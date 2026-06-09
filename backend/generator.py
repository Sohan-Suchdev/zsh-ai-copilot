import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Model constant — swap here to upgrade without touching call sites.
MODEL = "gpt-4o-mini"

# System prompt constrains the model strictly to raw bash output.
# No markdown, no explanation — only what the shell can execute directly.
SYSTEM_PROMPT = (
    "You are an expert Ubuntu bash command generator. "
    "Convert the user's natural language query into a single, raw, executable bash command. "
    "Output ONLY the command itself — no explanation, no markdown, no code fences."
)


def buildClient():
    """Initialise the OpenAI client using the API key from the environment."""
    apiKey = os.getenv("OPENAI_API_KEY")
    if not apiKey:
        raise EnvironmentError("OPENAI_API_KEY is not set in the environment or .env file.")
    return OpenAI(api_key=apiKey)


def generateCommand(query: str) -> str:
    """
    Convert a natural language query into an executable bash command.

    Uses a tightly-scoped system prompt so the model returns only the raw
    command string, making downstream parsing trivial and safe.
    """
    client = buildClient()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0,      # Deterministic output — commands should not vary.
        max_tokens=150,     # A single bash command never needs more than this.
    )

    rawCommand = response.choices[0].message.content.strip()
    return rawCommand
