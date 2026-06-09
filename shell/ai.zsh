# AI Copilot: thin client that forwards natural language queries to the local backend daemon.

BACKEND_URL="http://127.0.0.1:8000"

# Generate a unique session identifier once per terminal session.
# Tries nanosecond timestamp first (Linux), then uuidgen (macOS), then PID as fallback.
if [[ -z "$AI_COPILOT_THREAD_ID" ]]; then
    AI_COPILOT_THREAD_ID=$(date +%s%N 2>/dev/null || uuidgen 2>/dev/null || echo $$)
    export AI_COPILOT_THREAD_ID
fi

# Sends a single query to the backend and prints the suggested command to stdout.
# Returns 1 and prints an error to stderr if the backend request fails.
# Usage: _fetchCommand "queryText" "shellVersion"
function _fetchCommand() {
    local queryText="$1"
    local shellVersion="$2"

    local jsonPayload
    jsonPayload=$(python3 -c "
import sys, json
print(json.dumps({
    'query':    sys.argv[1],
    'context': {
        'pwd':   sys.argv[2],
        'shell': sys.argv[3]
    },
    'threadId': sys.argv[4]
}))
" "$queryText" "$PWD" "$shellVersion" "$AI_COPILOT_THREAD_ID")

    local rawResponse
    rawResponse=$(curl --silent --write-out "\n%{http_code}" \
        --request POST \
        --header "Content-Type: application/json" \
        --data "$jsonPayload" \
        "${BACKEND_URL}/query")

    local httpStatus
    httpStatus=$(echo "$rawResponse" | tail -n1)
    local responseBody
    responseBody=$(echo "$rawResponse" | head -n -1)

    if [[ "$httpStatus" -ne 200 ]]; then
        echo "Error: backend returned HTTP ${httpStatus}" >&2
        echo "$responseBody" >&2
        return 1
    fi

    # Parse and print the 'command' field; Python is always available in WSL.
    echo "$responseBody" | python3 -c "import sys,json; print(json.load(sys.stdin)['command'])"
}

# Sends a natural language query to the backend, prints the validated command,
# prompts for confirmation, and enters a self-correction loop on failure.
# Usage: ai "list all running docker containers"
function ai() {
    local queryText="$*"

    # Reject empty input early to avoid a malformed request.
    if [[ -z "$queryText" ]]; then
        echo "Usage: ai <your natural language query>" >&2
        return 1
    fi

    # Resolve the shell identifier — prefer a version string for richer context.
    local shellVersion
    if [[ -n "$ZSH_VERSION" ]]; then
        shellVersion="zsh ${ZSH_VERSION}"
    elif [[ -n "$BASH_VERSION" ]]; then
        shellVersion="bash ${BASH_VERSION}"
    else
        shellVersion="$(basename "$SHELL")"
    fi

    # Fetch the initial command from the backend.
    local suggestedCommand
    suggestedCommand=$(_fetchCommand "$queryText" "$shellVersion") || return 1

    # Execution and self-correction loop.
    # A while loop is used instead of recursion to avoid Zsh call-stack limits.
    while true; do
        echo "$suggestedCommand"

        # Read directly from /dev/tty so prompts work correctly inside pipelines.
        local userConfirmation
        printf "Execute this command? [Y/n] " > /dev/tty
        read -r userConfirmation < /dev/tty

        if [[ "$userConfirmation" != "y" && "$userConfirmation" != "Y" && -n "$userConfirmation" ]]; then
            echo "Aborted."
            return 0
        fi

        # Execute the command, routing stderr to a temp file so it can be read back.
        local stderrFile="/tmp/ai_copilot_stderr_$$"
        eval "$suggestedCommand" 2>"$stderrFile"
        local exitCode=$?

        if [[ $exitCode -eq 0 ]]; then
            rm -f "$stderrFile"
            return 0
        fi

        # Command failed — surface the error and offer auto-debug.
        local stderrContent
        stderrContent=$(cat "$stderrFile")
        rm -f "$stderrFile"

        echo "Command failed (exit code ${exitCode})." >&2
        [[ -n "$stderrContent" ]] && echo "$stderrContent" >&2

        local debugConfirmation
        printf "Auto-debug with AI? [Y/n] " > /dev/tty
        read -r debugConfirmation < /dev/tty

        if [[ "$debugConfirmation" != "y" && "$debugConfirmation" != "Y" && -n "$debugConfirmation" ]]; then
            return 1
        fi

        # Build the debug query — the session history already holds the failed command,
        # so the backend generator has full context to produce a corrected version.
        local debugQuery
        debugQuery="The last command '${suggestedCommand}' failed with exit code ${exitCode}. Error output: ${stderrContent}. Please write a corrected command."

        suggestedCommand=$(_fetchCommand "$debugQuery" "$shellVersion") || return 1
        # Loop: present the corrected command with the standard [Y/n] prompt.
    done
}
