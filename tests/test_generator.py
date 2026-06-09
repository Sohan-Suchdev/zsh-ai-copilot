from unittest.mock import MagicMock, patch
from backend.generator import generateCommand


def buildMockResponse(commandText: str) -> MagicMock:
    """Construct a mock that mirrors the shape of an OpenAI chat completion response."""
    mockMessage = MagicMock()
    mockMessage.content = commandText

    mockChoice = MagicMock()
    mockChoice.message = mockMessage

    mockResponse = MagicMock()
    mockResponse.choices = [mockChoice]
    return mockResponse


@patch("backend.generator.buildClient")
def test_generateCommand_returnsExpectedCommand(mockBuildClient):
    """Verify that generateCommand correctly extracts and returns the command string."""
    expectedCommand = "ls -la /home"
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse(expectedCommand)
    mockBuildClient.return_value = mockClient

    result = generateCommand("list all files in home directory")

    assert result == expectedCommand


@patch("backend.generator.buildClient")
def test_generateCommand_stripsWhitespace(mockBuildClient):
    """Verify that leading/trailing whitespace in the model response is stripped."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("  df -h  ")
    mockBuildClient.return_value = mockClient

    result = generateCommand("show disk usage")

    assert result == "df -h"


@patch("backend.generator.buildClient")
def test_generateCommand_passesQueryToModel(mockBuildClient):
    """Verify that the user query is forwarded to the model in the correct message role."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("uptime")
    mockBuildClient.return_value = mockClient

    generateCommand("show system uptime")

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "show system uptime"
