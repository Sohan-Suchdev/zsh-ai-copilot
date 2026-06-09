from unittest.mock import MagicMock, patch
from backend.generator import validatorNode, VALIDATOR_PROMPT

MOCK_CONTEXT = {"pwd": "/test/dir", "shell": "bash"}


def buildMockResponse(text: str) -> MagicMock:
    """Construct a mock mirroring the shape of an OpenAI chat completion response."""
    mockMessage = MagicMock()
    mockMessage.content = text
    mockChoice = MagicMock()
    mockChoice.message = mockMessage
    mockResponse = MagicMock()
    mockResponse.choices = [mockChoice]
    return mockResponse


def buildState(command: str, query: str = "test query", pastCommands: list = None) -> dict:
    """Return a fully-populated AgentState dict with the standard mock context."""
    return {
        "query": query,
        "context": MOCK_CONTEXT,
        "knowledgeBase": "",
        "osInfo": "",
        "isQuestion": False,
        "command": command,
        "response": "",
        "isValid": False,
        "rejectionReason": "",
        "pastCommands": pastCommands if pastCommands is not None else [],
    }


@patch("backend.generator.buildClient")
def test_validatorNode_safeCommandSetsIsValidTrue(mockBuildClient):
    """Verify that a SAFE verdict sets isValid to True and appends the command to pastCommands."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    result = validatorNode(buildState("ls -la"))

    # On SAFE, the node appends a Q/A pair so the generator can resolve pronouns across turns.
    assert result == {"isValid": True, "rejectionReason": "", "pastCommands": ["User: test query -> AI: ls -la"]}


@patch("backend.generator.buildClient")
def test_validatorNode_unsafeCommandSetsIsValidFalse(mockBuildClient):
    """Verify that an UNSAFE verdict sets isValid to False and populates rejectionReason."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("UNSAFE: Deletes the entire filesystem.")
    mockBuildClient.return_value = mockClient

    result = validatorNode(buildState("rm -rf /", query="nuke everything"))

    assert result == {"isValid": False, "rejectionReason": "Deletes the entire filesystem."}


@patch("backend.generator.buildClient")
def test_validatorNode_usesCorrectSystemPrompt(mockBuildClient):
    """Verify the node's system message contains VALIDATOR_PROMPT (after the context header)."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    validatorNode(buildState("ls -la"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    # The system message is contextHeader + VALIDATOR_PROMPT; check containment not equality.
    assert VALIDATOR_PROMPT in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_validatorNode_forwardsCommandAsUserMessage(mockBuildClient):
    """Verify the generated command (not the original query) is sent for validation."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    validatorNode(buildState("df -h", query="show disk usage"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "df -h"


@patch("backend.generator.buildClient")
def test_validatorNode_injectsContextIntoSystemMessage(mockBuildClient):
    """Verify that the pwd and shell from context appear in the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    validatorNode(buildState("ls -la"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "/test/dir" in systemMessage["content"]
    assert "bash" in systemMessage["content"]
