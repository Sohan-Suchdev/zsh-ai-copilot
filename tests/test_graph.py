import pytest
from unittest.mock import MagicMock, patch
from backend.generator import generateCommand


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
def test_fullGraph_returnsCommandWhenValidatorApproves(mockBuildClient):
    """Verify the full pipeline returns the command string on a SAFE verdict."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("ls -la")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("SAFE")

    # side_effect supplies a different client per call: first to generatorNode, second to validatorNode.
    mockBuildClient.side_effect = [generatorClient, validatorClient]

    result = generateCommand("list all files")

    assert result == "ls -la"


@patch("backend.generator.buildClient")
def test_fullGraph_raisesValueErrorWhenValidatorRejects(mockBuildClient):
    """Verify the full pipeline raises ValueError when the validator returns UNSAFE."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("rm -rf /")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("UNSAFE: Deletes the entire filesystem.")

    mockBuildClient.side_effect = [generatorClient, validatorClient]

    with pytest.raises(ValueError, match="Deletes the entire filesystem."):
        generateCommand("delete everything")


@patch("backend.generator.buildClient")
def test_fullGraph_generatorOutputIsPassedToValidator(mockBuildClient):
    """Verify the command produced by the generator is exactly what the validator receives."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("du -sh *")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("SAFE")

    mockBuildClient.side_effect = [generatorClient, validatorClient]

    generateCommand("show size of each item in current directory")

    validatorCallArgs = validatorClient.chat.completions.create.call_args
    messages = validatorCallArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "du -sh *"
