# zsh-ai-copilot

A terminal-native AI agent that converts natural language queries into validated, environment-aware bash commands. Built on a persistent FastAPI daemon, a LangGraph multi-node state machine, and a locally embedded ChromaDB knowledge base. The entire pipeline runs on-device with no cloud dependencies beyond the OpenAI API call.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Installation and Deployment](#2-installation-and-deployment)
3. [Operational Guide and Core Features](#3-operational-guide-and-core-features)
4. [Engineering Architecture Deep Dive](#4-engineering-architecture-deep-dive)
5. [Project Structure](#5-project-structure)
6. [Running the Test Suite](#6-running-the-test-suite)

---

## 1. System Overview

### Native Agent vs. Containerized Wrapper

The dominant pattern for AI-assisted terminals is a stateless web wrapper: an application accepts a text prompt, forwards it to a remote API, and prints the response. This architecture is disconnected from the execution environment by design. The model receives no information about the user's working directory, installed toolchain, shell version, OS distribution, or command history. Every response is a decontextualized guess calibrated for a generic Linux user.

`zsh-ai-copilot` is designed around a different constraint: the agent must know the environment it is generating commands for. A native daemon running on the local machine has direct, low-latency access to all state parameters relevant to command generation. It reads the current working directory from `$PWD`, the shell version from `$ZSH_VERSION` or `$BASH_VERSION`, the kernel and architecture from `uname -srm`, and the distribution name from `/etc/os-release`. This data is injected into the LLM system prompt as a structured context header on every request, before any generation token is produced.

The practical outcome is distribution-specific output without user annotation. A query for "install ffmpeg" on an Ubuntu system produces `sudo apt install ffmpeg`. On Fedora, the same query produces `sudo dnf install ffmpeg`. The model does not guess; it reads the value from the payload.

Local system access also enables session memory. The agent accumulates a history of validated Q/A command pairs scoped to the active terminal session via `MemorySaver`. This allows the generator to resolve forward and backward references across queries within the same session, such as "run that again on the subdirectory" following a previous `find` invocation.

### Daemon Architecture

The backend runs as a persistent Uvicorn/FastAPI process on `127.0.0.1:8000`. The shell client performs a TCP liveness check before every request using `nc -z`. If the port is not open, the client boots the server in the background using the project virtual environment and polls until the port is accepting connections. From the user's perspective, the server is always available. There is no manual startup step after installation.

Isolating the backend as a daemon rather than forking a Python process per invocation eliminates cold-start latency on repeated calls. The LangGraph state graph and ChromaDB vector store are initialized once at module load and reused across all requests within the session.

---

## 2. Installation and Deployment

### Prerequisites

| Dependency | Minimum Version | Notes |
|---|---|---|
| Python | 3.9 | 3.12 used in development |
| curl | any | standard on all major distributions |
| nc (netcat) | any | optional; client falls back to curl probe if absent |

### Automated Installation

The `install.sh` script in the project root performs a complete, idempotent installation. It is safe to run multiple times; each step checks for existing state before taking action.

```bash
chmod +x install.sh
./install.sh
```

The script executes five steps in order.

#### Step 1: Python 3 Verification

Confirms that `python3` is available in `PATH` and prints the version string. Exits immediately with a diagnostic message if not found. No system packages are modified.

#### Step 2: Virtual Environment and Dependency Installation

Creates `venv/` in the project root via `python3 -m venv`. Installs all dependencies from `requirements.txt` using `venv/bin/pip`. On subsequent runs, the existing `venv/` directory is detected and creation is skipped; only the pip install step runs, which is idempotent for pinned versions.

#### Step 3: API Key Configuration

Prompts for the OpenAI API key using `read -rs`. The `-s` flag suppresses terminal echo, so the key is never displayed as plain text during input. The key is written to `.env` in the project root as `OPENAI_API_KEY=<value>`. Before writing, the installer checks for an existing `^OPENAI_API_KEY=` entry via `grep -q`. A configured key is never overwritten on re-installation.

#### Step 4: Knowledge Directory Initialization

Creates `~/.ai-copilot-knowledge/` via `mkdir -p`. This directory is the input path for the local RAG ingestion pipeline. Placing `.txt` or `.md` files here and running the ingest step (see Section 3) populates the ChromaDB vector store with custom knowledge.

#### Step 5: Shell Runcom Configuration

Appends a `source` directive for `shell/ai.zsh` to both `~/.zshrc` and `~/.bashrc`. Before appending, the installer checks whether the absolute project path is already referenced in each file via `grep -qF`. The source line is never duplicated across multiple installation runs. Non-existent rc files are created with `touch` before the check.

The appended block takes this form:

```bash
# AI Copilot
source "/absolute/path/to/zsh-ai-copilot/shell/ai.zsh"
```

### Post-Installation

Open a new terminal or reload the active shell:

```bash
source ~/.zshrc   # Zsh
source ~/.bashrc  # Bash
```

The `ai` function is now available in the shell. The backend server starts automatically on the first invocation.

### Manual Installation Fallback

```bash
# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# API key
echo "OPENAI_API_KEY=your_key_here" > .env

# Knowledge directory
mkdir -p ~/.ai-copilot-knowledge

# Shell configuration (use the absolute path)
echo 'source "/absolute/path/to/zsh-ai-copilot/shell/ai.zsh"' >> ~/.zshrc
```

### Manual Server Start

The shell client handles server lifecycle automatically. To start the server manually for debugging or log monitoring:

```bash
source venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

When auto-started by the shell client, server output is appended to `uvicorn.log` in the project root.

---

## 3. Operational Guide and Core Features

### Scenario 1: Environment-Aware Command Generation

The agent reads distribution, shell, and working directory state before generating any command. No user annotation is required to produce distribution-correct output.

**Query:**

```
ai "install the requests library system-wide"
```

**Terminal state on Ubuntu 22.04:**

```
sudo pip3 install requests
Execute? [Y/n/e]
```

The generator receives the full context header including `Ubuntu 22.04.3 LTS` from `/etc/os-release` and the active Python version from the shell history. The model is called with `temperature=0`, so output is deterministic for identical environment state.

**Package manager targeting across distributions:**

```
ai "install the tree utility"
```

| OS (from /etc/os-release) | Generated command |
|---|---|
| Ubuntu / Debian | `sudo apt install tree` |
| Fedora / RHEL | `sudo dnf install tree` |
| Arch Linux | `sudo pacman -S tree` |
| macOS (Homebrew) | `brew install tree` |

The distribution string is embedded in the system prompt context header before the `GENERATOR_PROMPT` instructions. No conditional logic in application code selects the package manager; the LLM receives the OS string and produces the corresponding syntax.

**Session memory and pronoun resolution:**

Commands are accumulated as Q/A pairs in the session state. Within the same terminal session:

```
ai "find all log files larger than 100MB"
find / -name "*.log" -size +100M
Execute? [Y/n/e] Y

ai "delete them"
find / -name "*.log" -size +100M -delete
Execute? [Y/n/e]
```

The generator resolves "them" against the Q/A pair stored in `pastCommands` for the current `thread_id` checkpoint.

---

### Scenario 2: Local RAG Knowledge Ingestion

Custom documentation, internal deployment runbooks, or project-specific tooling conventions can be indexed into the local ChromaDB instance. Retrieved context is injected directly into the generator's system prompt. No document content leaves the machine.

**Step 1: Place source documents in the knowledge directory**

```bash
# Supported formats: .txt and .md
cp internal-deploy-runbook.md ~/.ai-copilot-knowledge/
cp custom-shell-aliases.txt ~/.ai-copilot-knowledge/
```

**Step 2: Run ingestion**

```bash
source venv/bin/activate
python3 -c "from backend.retriever import ingestDocuments; ingestDocuments()"
```

The ingester reads all `.txt` and `.md` files from `~/.ai-copilot-knowledge/` using `DirectoryLoader`, splits them into 500-character chunks with 50-character overlap via `RecursiveCharacterTextSplitter`, computes embeddings using `HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")`, and persists the resulting vectors to `db/chroma/`.

Expected output:

```
Ingested 47 chunks from 2 document(s) into db/chroma.
```

**Step 3: Query against ingested knowledge**

```
ai "run the staging deployment"
```

The `retrievalNode` performs a cosine similarity search against the vector store with `k=3`. If the runbook document contains a staging deployment procedure, the top 3 most semantically relevant chunks are concatenated and injected into the generator system prompt under the heading `Proprietary Local Knowledge`. The resulting command reflects the internal procedure rather than a generic template.

If the vector store is empty or the search returns no results, `getRelevantContext` returns an empty string and the generation pipeline proceeds without RAG context. The `knowledgeBase` injection block is omitted from the system prompt entirely when the string is empty.

---

### Scenario 3: Interactive Mutation Loop and Autonomous Self-Correction

The execution loop exposes three decision paths on every suggested command: execute, abort, or mutate inline. Failed executions are automatically routed back through the full generation pipeline with error context attached.

**Standard flow:**

```
ai "compress the logs directory into a tarball"

tar -czf logs.tar.gz logs/
Execute? [Y/n/e]
```

Pressing `Y` or `Enter` executes the command. Pressing `n` aborts with no side effects. Pressing `e` opens the command buffer for inline editing.

**Inline mutation:**

On Zsh, pressing `e` invokes `vared`, the native Zsh variable editor with full readline support, pre-populated with the suggested command:

```
Execute? [Y/n/e] e
tar -czf logs_2024.tar.gz logs/      # user edits buffer, then presses Enter
Execute? [Y/n/e]
```

On Bash, the same behavior is achieved via `read -e -i "$suggestedCommand"`. The modified command re-enters the confirmation loop rather than executing immediately.

**Autonomous self-correction on non-zero exit:**

When the executed command exits with a non-zero status code, the shell captures `stderr` to a temporary file at `/tmp/ai_copilot_stderr_$$`, displays the error output, and offers an automated debug cycle:

```
ai "tail the application log"

tail -f /var/log/myapp/app.log
Execute? [Y/n/e] Y
tail: cannot open '/var/log/myapp/app.log' for reading: No such file or directory
Command failed (exit code 1).
Auto-debug with AI? [Y/n]
```

Selecting `Y` constructs a debug query embedding the original command, exit code, and captured `stderr` content:

```
The last command 'tail -f /var/log/myapp/app.log' failed with exit code 1.
Error output: tail: cannot open '/var/log/myapp/app.log' for reading: No such file or directory.
Please write a corrected command.
```

This query is dispatched through the full LangGraph pipeline. The session's `pastCommands` already contains the failed command as a Q/A pair, giving the generator full context to produce a corrected version. The corrected command is presented in the same `[Y/n/e]` loop. The cycle repeats until the command succeeds or the user explicitly aborts.

Debug re-fetches always pass `isQuestion=false` in the payload, ensuring they are routed to the command generator rather than the explainer node.

**Question routing:**

Queries terminating with `?` are detected in the shell client before the request is sent. The `isQuestion=true` flag is included in the JSON payload. The LangGraph conditional router bypasses `generatorNode` and `validatorNode` entirely, routing directly to `explainerNode`. No command is produced, and the execution loop is skipped:

```
ai "what does the 2>/dev/null redirect do?"

The redirect 2>/dev/null sends file descriptor 2 (stderr) to /dev/null, discarding
all error output. File descriptor 1 (stdout) is unaffected. This is commonly used
to suppress error messages from commands like find or grep when permission errors
or missing paths are expected and irrelevant to the output.
```

---

## 4. Engineering Architecture Deep Dive

### Full Execution Pipeline

The following diagram traces a complete invocation from terminal input to final state resolution across both execution paths.

```
User: ai "query text"
         |
         v
+--------------------------------+
|   shell/ai.zsh :: ai()         |
+--------------------------------+
         |
         v
+--------------------------------+
| _ensureBackendRunning()         |
|                                 |
|  _isPortOpen()                  |
|  nc -z 127.0.0.1 8000           |
|                                 |
|  [Open]  --> continue           |
|  [Closed]                       |
|    |                            |
|    v                            |
|  nohup venv/bin/uvicorn         |
|    backend.main:app             |
|    >> uvicorn.log 2>&1 &        |
|                                 |
|  poll _isPortOpen() every 1s    |
|  max 10 attempts                |
|    |                            |
|  [Timeout] --> error, return 1  |
|  [Ready]   --> return 0         |
+--------------------------------+
         |
         v
  Detect: shellVersion
          osInfo (uname -srm + /etc/os-release)
          isQuestion (query string ends with '?')
         |
         v
+--------------------------------+
|  _fetchCommand()                |
|                                 |
|  Build JSON payload via         |
|  python3 sys.argv (injection-   |
|  safe; no shell interpolation   |
|  into JSON strings)             |
|                                 |
|  POST /query                    |
|  Content-Type: application/json |
+--------------------------------+
         |
         v
+--------------------------------+
|  FastAPI :: handleQuery()       |
|  Pydantic QueryRequest          |
|  validation                     |
|                                 |
|  Fields:                        |
|    query:      str              |
|    context:    {pwd, shell}     |
|    threadId:   str              |
|    osInfo:     str              |
|    isQuestion: bool             |
+--------------------------------+
         |
         v
+--------------------------------+
|  generateCommand()              |
|  Initialise AgentState          |
|  _graph.invoke(initialState,    |
|    thread_id=threadId)          |
+--------------------------------+
         |
         v
+--------------------------------+
|   retrievalNode                 |
|                                 |
|  ChromaDB.similarity_search     |
|  query=state["query"], k=3      |
|  model: all-MiniLM-L6-v2        |
|  (runs locally via              |
|   sentence-transformers)        |
|                                 |
|  Returns knowledgeBase: str     |
|  (empty string on miss or error)|
+--------------------------------+
         |
         v
+--------------------------------+
|  routeQuery()                   |
|  [conditional edge on           |
|   retrievalNode]                |
|                                 |
|  reads state["isQuestion"]      |
+-----+----------------------+----+
      |                      |
   True                   False
      |                      |
      v                      v
+-----------+      +--------------------+
|explainer  |      |  generatorNode     |
|Node       |      |                    |
|           |      |  System prompt:    |
|EXPLAINER  |      |  1. Context header |
|_PROMPT    |      |     - pwd          |
|           |      |     - shell        |
|+ context  |      |     - osInfo       |
|+ osInfo   |      |     - pastCommands |
|+ knowledge|      |       (last 5)     |
|           |      |  2. GENERATOR_     |
|temp=0     |      |     PROMPT         |
|max=500    |      |  3. knowledgeBase  |
|tokens     |      |     (if non-empty) |
|           |      |                    |
|           |      |  gpt-4o-mini       |
|           |      |  temp=0, max=150   |
+-----+-----+      +--------+-----------+
      |                      |
      v                      v
{"response": str,   +--------------------+
 "isValid": True}   |  validatorNode     |
      |             |                    |
      |             |  VALIDATOR_PROMPT  |
      |             |  Verdict string:   |
      |             |  "SAFE"            |
      |             |  "UNSAFE: <reason>"|
      |             |                    |
      |             |  temp=0, max=60    |
      |             +--------+-----------+
      |                      |
      |             +--------+-----------+
      |             |  On SAFE:          |
      |             |  pastCommands +=   |
      |             |  ["User: Q -> AI:C"]
      |             |  isValid = True    |
      |             +--------+-----------+
      |                      |
      +----------+-----------+
                 |
                 v
      finalState["isQuestion"]?
      /                        \
   True                       False
      |                          |
 return response           isValid = True?
   to endpoint              /           \
                          True          False
                            |              |
                     return command    raise ValueError
                     to endpoint       HTTP 422
                                       shell prints error
                                       and returns 1
```

### State Schema

All data flows through a single `AgentState` TypedDict. Each node returns a partial dict; LangGraph merges it into the current checkpoint snapshot via field-level reducers. No node holds or mutates a global object.

```python
class AgentState(TypedDict):
    query:           str
    # {pwd: str, shell: str} -- sampled at invocation time
    context:         dict
    # e.g. "Linux 5.15.0-91 x86_64 / Ubuntu 22.04.3 LTS"
    osInfo:          str
    # True when query string terminates with '?'
    isQuestion:      bool
    # Concatenated RAG chunks; empty string if store is empty or search misses
    knowledgeBase:   str
    # Raw bash command produced by generatorNode
    command:         str
    # Natural language answer produced by explainerNode
    response:        str
    # Safety verdict from validatorNode; True on SAFE
    isValid:         bool
    # Human-readable rejection reason; empty string on SAFE verdict
    rejectionReason: str
    # Append-only reducer: operator.add merges new entries into the MemorySaver
    # checkpoint without overwriting existing history across invocations
    pastCommands:    Annotated[list, operator.add]
```

The `pastCommands` field is the primary mechanism for cross-turn context. `operator.add` is registered as a LangGraph field reducer. When `_graph.invoke()` completes and writes back to the `MemorySaver` checkpoint for a given `thread_id`, the new list is concatenated onto the existing one rather than replacing it. Passing an empty list `[]` in `initialState` on each invocation leaves the existing history intact. Each validated command is stored as `"User: <query> -> AI: <command>"` so the generator receives readable Q/A history rather than raw command strings, enabling pronoun resolution across turns.

### Node Responsibilities

**`retrievalNode`**

Calls `getRelevantContext(query)`, which performs `ChromaDB.similarity_search(query, k=3)` using `all-MiniLM-L6-v2` embeddings computed locally by `sentence-transformers`. The vector store is persisted at `db/chroma/` and loaded on each call to `_getVectorStore()`. All exceptions are caught; the function returns an empty string on any failure, including an uninitialized store. No exception propagates out of this node.

**`routeQuery`**

A stateless routing function attached as a conditional edge on `retrievalNode`. Reads `state["isQuestion"]` and returns either `"explainerNode"` or `"generatorNode"`. LangGraph resolves the return value against the path map defined in `_buildGraph()`. This function performs no I/O and has no side effects.

**`generatorNode`**

Assembles a system prompt from components in sequence: the environment context header (pwd, shell, osInfo, and the 5 most recent `pastCommands` entries), the `GENERATOR_PROMPT` constant, and optionally the RAG context block (omitted when `knowledgeBase` is empty). Calls `gpt-4o-mini` with `temperature=0` and `max_tokens=150`. Returns `{"command": str}`.

**`validatorNode`**

Receives the generated command as the LLM user message. Instructs the model via `VALIDATOR_PROMPT` to respond with exactly `"SAFE"` or `"UNSAFE: <reason>"`. `max_tokens=60` enforces the short verdict format. On `SAFE`, appends the formatted Q/A pair to `pastCommands` and sets `isValid=True`. On `UNSAFE`, strips the prefix and populates `rejectionReason`. The prompt explicitly instructs the model not to reject commands solely because referenced paths might not exist at runtime; runtime errors are handled by the shell self-correction loop.

**`explainerNode`**

Structurally identical to `generatorNode` but uses `EXPLAINER_PROMPT` and `max_tokens=500`. Injects osInfo and knowledge base context via the same code paths. Returns `{"response": str, "isValid": True}`. Setting `isValid=True` in the return value causes `generateCommand` to return the response string directly, without requiring any branch on node identity in the return logic.

### Graph Topology

```python
graph.set_entry_point("retrievalNode")
graph.add_conditional_edges("retrievalNode", routeQuery, {
    "generatorNode": "generatorNode",
    "explainerNode": "explainerNode",
})
graph.add_edge("generatorNode", "validatorNode")
graph.add_edge("validatorNode", END)
graph.add_edge("explainerNode", END)
```

The graph is compiled once at module load time (`_graph = _buildGraph()`) and reused on every `generateCommand` call. `MemorySaver` is instantiated once at module level as `_memory` and passed to `graph.compile(checkpointer=_memory)`.

### Session Isolation

Each terminal session exports `AI_COPILOT_THREAD_ID` at shell load time, generated from `date +%s%N` (nanosecond-precision timestamp on Linux), `uuidgen` (macOS), or `$$` (PID fallback). This value is transmitted as `threadId` on every request. `MemorySaver` uses `thread_id` as the checkpoint partition key. Sessions running in separate terminal windows maintain independent `pastCommands` histories with no shared state.

### Determinism

All LLM calls are issued with `temperature=0`. For a fixed system prompt and identical session state, the generator and validator produce the same output across invocations. The session history passed to the context header is bounded to the 5 most recent Q/A pairs, preventing unbounded prompt growth across long sessions.

### Security Model

The `VALIDATOR_PROMPT` is the primary safety boundary. It rejects commands that cause irreversible filesystem damage, data loss, privilege escalation, or network exfiltration. Commands that reference non-existent paths are explicitly passed through; the shell handles runtime errors through the self-correction loop.

The API key is never interpolated into Python source strings or shell command arguments. `install.sh` reads the key using `read -rs` with no terminal echo. The key is stored in `.env` and loaded at runtime via `python-dotenv`. No key value appears in logs, system prompt text, or network payloads.

ChromaDB stores all vector data at `db/chroma/` on the local filesystem. No document content or embedding vectors are transmitted to external services.

JSON payloads are constructed by passing all user-supplied values as `sys.argv` positional arguments to an inline Python process, which serializes them with `json.dumps`. Shell variable interpolation into JSON strings is never used, eliminating a class of injection vulnerabilities that affect `sed`-based escaping approaches.

---

## 5. Project Structure

```
zsh-ai-copilot/
├── backend/
│   ├── generator.py       # LangGraph state machine: AgentState, all nodes, graph topology
│   ├── main.py            # FastAPI application: QueryRequest schema, /query endpoint
│   └── retriever.py       # ChromaDB interface: ingestion pipeline, similarity retrieval
├── shell/
│   └── ai.zsh             # Shell client: TCP probe, auto-boot, context detection, execution loop
├── tests/
│   ├── test_generator_node.py   # Unit tests for generatorNode
│   ├── test_validator_node.py   # Unit tests for validatorNode
│   ├── test_explainer_node.py   # Unit tests for explainerNode
│   ├── test_graph.py            # Integration tests for generateCommand (full graph)
│   ├── test_generator.py        # Integration tests for generateCommand (public API)
│   └── test_main.py             # Endpoint tests via FastAPI TestClient
├── db/
│   └── chroma/            # Persistent ChromaDB vector store (git-ignored)
├── install.sh             # Idempotent installer
├── start.sh               # Manual server launch shortcut
├── requirements.txt       # Pinned dependency manifest
└── .env                   # API key file (git-ignored)
```

---

## 6. Running the Test Suite

```bash
source venv/bin/activate
pytest tests/ -v
```

All tests use `unittest.mock.patch` to replace `buildClient` and `getRelevantContext`. No OpenAI API calls and no ChromaDB reads occur during the test run. `HuggingFaceEmbeddings` is never instantiated because `getRelevantContext` is patched at the module boundary before any import-time model load can occur.

The LangGraph graph is exercised end-to-end in `test_graph.py` with mocked LLM clients, verifying state propagation through the full pipeline, conditional routing on `isQuestion`, `pastCommands` accumulation across the `MemorySaver` checkpoint, and `ValueError` propagation on `UNSAFE` verdicts.

Node-level tests in `test_generator_node.py`, `test_validator_node.py`, and `test_explainer_node.py` call node functions directly with fully populated `AgentState` dicts, verifying prompt assembly, field injection order, and return value structure without invoking the graph.
