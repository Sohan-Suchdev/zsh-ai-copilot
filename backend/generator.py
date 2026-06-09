import os
import operator
from typing import Annotated, TypedDict
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from backend.retriever import getRelevantContext

load_dotenv()

MODEL = "gpt-4o-mini"

# Base instructions for each node — context, session history, and RAG knowledge are prepended at runtime.
GENERATOR_PROMPT = (
    "You are an expert Ubuntu bash command generator. "
    "Convert the user's natural language query into a single, raw, executable bash command "
    "that is correct for their current environment. "
    "Output ONLY the command itself — no explanation, no markdown, no code fences. "
    "CRITICAL RULES — follow in strict order: "
    "1. NEVER preemptively assume a file, directory, or resource does not exist. "
    "   Always generate the direct bash command the user asked for on the first attempt. "
    "2. ONLY generate an `echo` explanation if the user's query explicitly contains a terminal "
    "   error message (e.g., 'No such file or directory', 'command not found') proving a "
    "   previous attempt already failed. "
    "3. When rule 2 applies, you may chain `echo 'explanation'` with `&&` and a helpful "
    "   fallback command (e.g., `echo 'Directory not found: listing current directory' && ls`)."
)

VALIDATOR_PROMPT = (
    "You are a Ubuntu bash security auditor focused exclusively on preventing irreversible harm. "
    "Evaluate the given bash command and respond with exactly one of two verdicts. "
    "Respond SAFE if the command is valid Ubuntu bash, regardless of whether files, directories, "
    "or packages referenced in it actually exist — execution errors are safe and handled by the shell. "
    "Respond UNSAFE: <brief reason> ONLY if the command would cause irreversible damage, data loss, "
    "system instability, or a security breach (e.g., `rm -rf`, disk wipes, reading `/etc/shadow`, "
    "privilege escalation, or network exfiltration). "
    "NEVER reject a command solely because a path or resource might not exist at runtime."
)

EXPLAINER_PROMPT = (
    "You are an expert Ubuntu bash assistant. "
    "The user has asked a question rather than requesting a command. "
    "Answer concisely and accurately. You may use markdown formatting for clarity. "
    "Do not produce a standalone bash command as your entire answer unless a command is the direct answer to the question."
)


class AgentState(TypedDict):
    query: str            # Original user input — immutable throughout the graph.
    context: dict         # Terminal environment snapshot: pwd and shell.
    knowledgeBase: str    # RAG context retrieved from the local Chroma knowledge base.
    osInfo: str           # OS/distro string from the shell (e.g., "Linux 5.15 x86_64 / Ubuntu 22.04").
    isQuestion: bool      # True when the query ends with '?' — routes to explainerNode.
    command: str          # Bash command produced by generatorNode.
    response: str         # Natural language answer produced by explainerNode.
    isValid: bool         # Safety verdict from validatorNode.
    rejectionReason: str  # Populated on rejection; empty string otherwise.
    # operator.add reducer appends new entries rather than replacing the list,
    # so MemorySaver accumulates validated commands across invocations of the same thread.
    pastCommands: Annotated[list, operator.add]


def buildClient() -> OpenAI:
    """Initialise the OpenAI client using the API key from the environment."""
    apiKey = os.getenv("OPENAI_API_KEY")
    if not apiKey:
        raise EnvironmentError("OPENAI_API_KEY is not set in the environment or .env file.")
    return OpenAI(api_key=apiKey)


def buildContextHeader(context: dict, pastCommands: list, osInfo: str = "") -> str:
    """Formats the terminal environment, OS info, and session history into a preamble for system prompts."""
    pwdValue = context.get("pwd", "unknown")
    shellValue = context.get("shell", "unknown")
    header = (
        f"User's current environment:\n"
        f"- Working directory: {pwdValue}\n"
        f"- Shell: {shellValue}\n"
    )
    if osInfo:
        header += f"- OS: {osInfo}\n"
    if pastCommands:
        # Limit to the 5 most recent turns to keep the prompt concise.
        recentTurns = pastCommands[-5:]
        historyLines = "\n".join(f"  - {turn}" for turn in recentTurns)
        header += f"- Recent session history:\n{historyLines}\n"
    return header + "\n"


def retrievalNode(state: AgentState) -> dict:
    """Queries the local ChromaDB knowledge base to enrich the generator's context."""
    relevantContext = getRelevantContext(state["query"])
    return {"knowledgeBase": relevantContext}


def routeQuery(state: AgentState) -> str:
    """Routes question queries to explainerNode and command requests to generatorNode."""
    return "explainerNode" if state.get("isQuestion") else "generatorNode"


def generatorNode(state: AgentState) -> dict:
    """Calls the LLM to convert the natural language query into a raw bash command."""
    client = buildClient()
    contextHeader = buildContextHeader(state["context"], state.get("pastCommands", []), state.get("osInfo", ""))

    systemContent = contextHeader + GENERATOR_PROMPT
    # Inject RAG knowledge only when the retrieval node found relevant content.
    if state.get("knowledgeBase"):
        systemContent += f"\n\nProprietary Local Knowledge:\n{state['knowledgeBase']}"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": systemContent},
            {"role": "user", "content": state["query"]},
        ],
        temperature=0,    # Deterministic output — commands must not vary between calls.
        max_tokens=150,
    )
    rawCommand = response.choices[0].message.content.strip()
    return {"command": rawCommand}


def validatorNode(state: AgentState) -> dict:
    """Audits the generated command for safety and validity given the user's environment."""
    client = buildClient()
    contextHeader = buildContextHeader(state["context"], state.get("pastCommands", []))
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": contextHeader + VALIDATOR_PROMPT},
            {"role": "user", "content": state["command"]},
        ],
        temperature=0,
        max_tokens=60,    # Verdict is always short: "SAFE" or "UNSAFE: <reason>".
    )
    verdict = response.choices[0].message.content.strip()

    if verdict == "SAFE":
        # Store as a Q/A pair so the generator can resolve pronouns across turns.
        historyEntry = f"User: {state['query']} -> AI: {state['command']}"
        return {"isValid": True, "rejectionReason": "", "pastCommands": [historyEntry]}

    # Strip the "UNSAFE:" prefix to isolate the human-readable reason.
    reason = verdict.removeprefix("UNSAFE:").strip()
    return {"isValid": False, "rejectionReason": reason}


def explainerNode(state: AgentState) -> dict:
    """Calls the LLM to answer a natural language question about the terminal environment."""
    client = buildClient()
    contextHeader = buildContextHeader(state["context"], state.get("pastCommands", []), state.get("osInfo", ""))

    systemContent = contextHeader + EXPLAINER_PROMPT
    if state.get("knowledgeBase"):
        systemContent += f"\n\nProprietary Local Knowledge:\n{state['knowledgeBase']}"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": systemContent},
            {"role": "user", "content": state["query"]},
        ],
        temperature=0,
        max_tokens=500,
    )
    return {"response": response.choices[0].message.content.strip(), "isValid": True}


# In-memory checkpointer — persists state across invocations sharing the same thread_id.
_memory = MemorySaver()


def _buildGraph():
    """Compiles the LangGraph state machine: retrievalNode → (generatorNode → validatorNode | explainerNode)."""
    graph = StateGraph(AgentState)
    graph.add_node("retrievalNode", retrievalNode)
    graph.add_node("generatorNode", generatorNode)
    graph.add_node("validatorNode", validatorNode)
    graph.add_node("explainerNode", explainerNode)
    graph.set_entry_point("retrievalNode")
    graph.add_conditional_edges("retrievalNode", routeQuery, {
        "generatorNode": "generatorNode",
        "explainerNode": "explainerNode",
    })
    graph.add_edge("generatorNode", "validatorNode")
    graph.add_edge("validatorNode", END)
    graph.add_edge("explainerNode", END)
    return graph.compile(checkpointer=_memory)


# Compiled once at module load and reused on every generateCommand call.
_graph = _buildGraph()


def generateCommand(query: str, context: dict, threadId: str, osInfo: str = "", isQuestion: bool = False) -> str:
    """
    Public entry point. Routes the query through:
    - Retrieval → Explainer (for questions ending with '?')
    - Retrieval → Generator → Validator (for command requests)

    Returns the validated bash command or the natural language explanation.
    threadId scopes the MemorySaver checkpoint so each terminal session maintains
    its own independent command history.

    Raises ValueError if the validator rejects the generated command.
    """
    initialState: AgentState = {
        "query": query,
        "context": context,
        "knowledgeBase": "",
        "osInfo": osInfo,
        "isQuestion": isQuestion,
        "command": "",
        "response": "",
        "isValid": False,
        "rejectionReason": "",
        "pastCommands": [],    # Empty list + operator.add leaves existing history intact.
    }
    finalState = _graph.invoke(
        initialState,
        config={"configurable": {"thread_id": threadId}},
    )

    # Question path — return the explanation directly, bypassing the validator check.
    if finalState.get("isQuestion"):
        return finalState["response"]

    if not finalState["isValid"]:
        raise ValueError(f"Command rejected by validator: {finalState['rejectionReason']}")

    return finalState["command"]
