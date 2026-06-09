# AI Copilot: thin client that forwards natural language queries to the local backend daemon.

BACKEND_URL="http://127.0.0.1:8000"

# Sends a natural language query to the backend, prints the validated command,
# and prompts the user to confirm before executing it.
# Usage: ai "list all running docker containers"
function ai() {
    local queryText="$*"

    # Reject empty input early to avoid a malformed request.
    if [[ -z "$queryText" ]]; then
        echo "Usage: ai <your natural language query>" >&2
        return 1
    fi

    # Safely encode the query into valid JSON using Python to prevent injection/escaping errors.
    local jsonPayload
    jsonPayload=$(python3 -c "import sys, json; print(json.dumps({'query': sys.argv[1]}))" "$queryText")

    # POST to the backend; capture both the response body and the HTTP status code.
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

    # Surface backend errors clearly rather than silently returning bad output.
    if [[ "$httpStatus" -ne 200 ]]; then
        echo "Error: backend returned HTTP ${httpStatus}" >&2
        echo "$responseBody" >&2
        return 1
    fi

    # Parse the 'command' field from the JSON response using Python,
    # which is always available in the WSL environment and avoids a jq dependency.
    local suggestedCommand
    suggestedCommand=$(echo "$responseBody" | python3 -c "import sys,json; print(json.load(sys.stdin)['command'])")

    echo "$suggestedCommand"

    # Read directly from /dev/tty so the prompt works correctly even when the
    # function is invoked inside a pipeline where stdin is not the terminal.
    local userConfirmation
    printf "Execute this command? [Y/n] " > /dev/tty
    read -r userConfirmation < /dev/tty

    if [[ "$userConfirmation" == "y" || "$userConfirmation" == "Y" || -z "$userConfirmation" ]]; then
        eval "$suggestedCommand"
    else
        echo "Aborted."
        return 0
    fi
}
