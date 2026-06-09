from unittest.mock import MagicMock, patch
from backend.generator import generatorNode, GENERATOR_PROMPT

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


def buildState(query: str = "list all files", command: str = "") -> dict:
    """Return a fully-populated AgentState dict with the standard mock context."""
    return {"query": query, "context": MOCK_CONTEXT, "command": command, "isValid": False, "rejectionReason": ""}


@patch("backend.generator.buildClient")
def test_generatorNode_populatesCommandFromModel(mockBuildClient):
    """Verify the node writes the model's response into the command state key."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ls -la")
    mockBuildClient.return_value = mockClient

    result = generatorNode(buildState("list all files"))

    assert result == {"command": "ls -la"}


@patch("backend.generator.buildClient")
def test_generatorNode_stripsWhitespace(mockBuildClient):
    """Verify that leading/trailing whitespace in the model response is stripped."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("  df -h  ")
    mockBuildClient.return_value = mockClient

    result = generatorNode(buildState("show disk usage"))

    assert result == {"command": "df -h"}


@patch("backend.generator.buildClient")
def test_generatorNode_usesCorrectSystemPrompt(mockBuildClient):
    """Verify the node's system message contains GENERATOR_PROMPT (after the context header)."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("uptime")
    mockBuildClient.return_value = mockClient

    generatorNode(buildState("show uptime"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    # The system message is contextHeader + GENERATOR_PROMPT; check containment not equality.
    assert GENERATOR_PROMPT in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_generatorNode_forwardsQueryAsUserMessage(mockBuildClient):
    """Verify the user query is forwarded in the user-role message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ps aux")
    mockBuildClient.return_value = mockClient

    generatorNode(buildState("show running processes"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "show running processes"


@patch("backend.generator.buildClient")
def test_generatorNode_injectsContextIntoSystemMessage(mockBuildClient):
    """Verify that the pwd and shell from context appear in the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ls")
    mockBuildClient.return_value = mockClient

    generatorNode(buildState("list files"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "/test/dir" in systemMessage["content"]
    assert "bash" in systemMessage["content"]
