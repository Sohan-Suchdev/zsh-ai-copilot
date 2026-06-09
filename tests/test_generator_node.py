from unittest.mock import MagicMock, patch
from backend.generator import generatorNode, GENERATOR_PROMPT


def buildMockResponse(text: str) -> MagicMock:
    """Construct a mock mirroring the shape of an OpenAI chat completion response."""
    mockMessage = MagicMock()
    mockMessage.content = text
    mockChoice = MagicMock()
    mockChoice.message = mockMessage
    mockResponse = MagicMock()
    mockResponse.choices = [mockChoice]
    return mockResponse


@patch("backend.generator.buildClient")
def test_generatorNode_populatesCommandFromModel(mockBuildClient):
    """Verify the node writes the model's response into the command state key."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ls -la")
    mockBuildClient.return_value = mockClient

    result = generatorNode({"query": "list all files", "command": "", "isValid": False, "rejectionReason": ""})

    assert result == {"command": "ls -la"}


@patch("backend.generator.buildClient")
def test_generatorNode_stripsWhitespace(mockBuildClient):
    """Verify that leading/trailing whitespace in the model response is stripped."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("  df -h  ")
    mockBuildClient.return_value = mockClient

    result = generatorNode({"query": "show disk usage", "command": "", "isValid": False, "rejectionReason": ""})

    assert result == {"command": "df -h"}


@patch("backend.generator.buildClient")
def test_generatorNode_usesCorrectSystemPrompt(mockBuildClient):
    """Verify the node sends GENERATOR_PROMPT as the system message, not the validator prompt."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("uptime")
    mockBuildClient.return_value = mockClient

    generatorNode({"query": "show uptime", "command": "", "isValid": False, "rejectionReason": ""})

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert systemMessage["content"] == GENERATOR_PROMPT


@patch("backend.generator.buildClient")
def test_generatorNode_forwardsQueryAsUserMessage(mockBuildClient):
    """Verify the user query is forwarded in the user-role message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ps aux")
    mockBuildClient.return_value = mockClient

    generatorNode({"query": "show running processes", "command": "", "isValid": False, "rejectionReason": ""})

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "show running processes"
