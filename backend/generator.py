import os
from typing import TypedDict
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

load_dotenv()

MODEL = "gpt-4o-mini"

# Base instructions for each node — context is prepended at runtime via buildContextHeader.
GENERATOR_PROMPT = (
    "You are an expert Ubuntu bash command generator. "
    "Convert the user's natural language query into a single, raw, executable bash command "
    "that is correct for their current environment. "
    "Output ONLY the command itself — no explanation, no markdown, no code fences."
)

VALIDATOR_PROMPT = (
    "You are a strict Ubuntu bash security auditor. "
    "Evaluate the given bash command in the context of the user's current environment. "
    "If the command is safe and valid Ubuntu bash, respond with exactly: SAFE\n"
    "If the command is unsafe or invalid, respond with exactly: UNSAFE: <brief reason>"
)


class AgentState(TypedDict):
    query: str            # Original user input — immutable throughout the graph.
    context: dict         # Terminal environment snapshot: pwd and shell.
    command: str          # Bash command produced by generatorNode.
    isValid: bool         # Safety verdict from validatorNode.
    rejectionReason: str  # Populated on rejection; empty string otherwise.


def buildClient() -> OpenAI:
    """Initialise the OpenAI client using the API key from the environment."""
    apiKey = os.getenv("OPENAI_API_KEY")
    if not apiKey:
        raise EnvironmentError("OPENAI_API_KEY is not set in the environment or .env file.")
    return OpenAI(api_key=apiKey)


def buildContextHeader(context: dict) -> str:
    """Formats the terminal environment snapshot into a preamble for system prompts."""
    pwdValue = context.get("pwd", "unknown")
    shellValue = context.get("shell", "unknown")
    return (
        f"User's current environment:\n"
        f"- Working directory: {pwdValue}\n"
        f"- Shell: {shellValue}\n\n"
    )


def generatorNode(state: AgentState) -> dict:
    """Calls the LLM to convert the natural language query into a raw bash command."""
    client = buildClient()
    contextHeader = buildContextHeader(state["context"])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": contextHeader + GENERATOR_PROMPT},
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
    contextHeader = buildContextHeader(state["context"])
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
        return {"isValid": True, "rejectionReason": ""}

    # Strip the "UNSAFE:" prefix to isolate the human-readable reason.
    reason = verdict.removeprefix("UNSAFE:").strip()
    return {"isValid": False, "rejectionReason": reason}


def _buildGraph():
    """Compiles the LangGraph state machine: generatorNode -> validatorNode."""
    graph = StateGraph(AgentState)
    graph.add_node("generatorNode", generatorNode)
    graph.add_node("validatorNode", validatorNode)
    graph.set_entry_point("generatorNode")
    graph.add_edge("generatorNode", "validatorNode")
    graph.add_edge("validatorNode", END)
    return graph.compile()


# Compiled once at module load and reused on every generateCommand call.
_graph = _buildGraph()


def generateCommand(query: str, context: dict) -> str:
    """
    Public entry point. Runs the query and terminal context through the
    Generator -> Validator state machine and returns the validated bash command.

    Raises ValueError if the validator rejects the generated command.
    """
    initialState: AgentState = {
        "query": query,
        "context": context,
        "command": "",
        "isValid": False,
        "rejectionReason": "",
    }
    finalState = _graph.invoke(initialState)

    if not finalState["isValid"]:
        raise ValueError(f"Command rejected by validator: {finalState['rejectionReason']}")

    return finalState["command"]
