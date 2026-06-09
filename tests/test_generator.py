from unittest.mock import MagicMock, patch
from backend.generator import generateCommand

MOCK_CONTEXT = {"pwd": "/test/dir", "shell": "bash"}
MOCK_THREAD_ID = "test-thread"


def buildMockResponse(text: str) -> MagicMock:
    """Construct a mock that mirrors the shape of an OpenAI chat completion response."""
    mockMessage = MagicMock()
    mockMessage.content = text
    mockChoice = MagicMock()
    mockChoice.message = mockMessage
    mockResponse = MagicMock()
    mockResponse.choices = [mockChoice]
    return mockResponse


def buildClientPair(commandText: str, verdict: str = "SAFE"):
    """
    Return a (generatorClient, validatorClient) pair for side_effect injection.
    The graph calls buildClient once per node, so each node gets its own client.
    """
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse(commandText)

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse(verdict)

    return generatorClient, validatorClient


@patch("backend.generator.buildClient")
def test_generateCommand_returnsExpectedCommand(mockBuildClient):
    """Verify that generateCommand correctly extracts and returns the command string."""
    generatorClient, validatorClient = buildClientPair("ls -la /home")
    mockBuildClient.side_effect = [generatorClient, validatorClient]

    result = generateCommand("list all files in home directory", MOCK_CONTEXT, MOCK_THREAD_ID)

    assert result == "ls -la /home"


@patch("backend.generator.buildClient")
def test_generateCommand_stripsWhitespace(mockBuildClient):
    """Verify that leading/trailing whitespace in the model response is stripped."""
    generatorClient, validatorClient = buildClientPair("  df -h  ")
    mockBuildClient.side_effect = [generatorClient, validatorClient]

    result = generateCommand("show disk usage", MOCK_CONTEXT, MOCK_THREAD_ID)

    assert result == "df -h"


@patch("backend.generator.buildClient")
def test_generateCommand_passesQueryToModel(mockBuildClient):
    """Verify that the user query is forwarded to the generator in the correct message role."""
    generatorClient, validatorClient = buildClientPair("uptime")
    mockBuildClient.side_effect = [generatorClient, validatorClient]

    generateCommand("show system uptime", MOCK_CONTEXT, MOCK_THREAD_ID)

    # Assert against the generator client — the validator receives the command, not the query.
    callArgs = generatorClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "show system uptime"
