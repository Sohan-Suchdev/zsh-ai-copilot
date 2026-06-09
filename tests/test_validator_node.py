from unittest.mock import MagicMock, patch
from backend.generator import validatorNode, VALIDATOR_PROMPT


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
def test_validatorNode_safeCommandSetsIsValidTrue(mockBuildClient):
    """Verify that a SAFE verdict sets isValid to True and clears rejectionReason."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    result = validatorNode({"query": "list files", "command": "ls -la", "isValid": False, "rejectionReason": ""})

    assert result == {"isValid": True, "rejectionReason": ""}


@patch("backend.generator.buildClient")
def test_validatorNode_unsafeCommandSetsIsValidFalse(mockBuildClient):
    """Verify that an UNSAFE verdict sets isValid to False and populates rejectionReason."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("UNSAFE: Deletes the entire filesystem.")
    mockBuildClient.return_value = mockClient

    result = validatorNode({"query": "nuke everything", "command": "rm -rf /", "isValid": False, "rejectionReason": ""})

    assert result == {"isValid": False, "rejectionReason": "Deletes the entire filesystem."}


@patch("backend.generator.buildClient")
def test_validatorNode_usesCorrectSystemPrompt(mockBuildClient):
    """Verify the node sends VALIDATOR_PROMPT as the system message, not the generator prompt."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    validatorNode({"query": "list files", "command": "ls -la", "isValid": False, "rejectionReason": ""})

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert systemMessage["content"] == VALIDATOR_PROMPT


@patch("backend.generator.buildClient")
def test_validatorNode_forwardsCommandAsUserMessage(mockBuildClient):
    """Verify the generated command (not the original query) is sent for validation."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("SAFE")
    mockBuildClient.return_value = mockClient

    validatorNode({"query": "show disk usage", "command": "df -h", "isValid": False, "rejectionReason": ""})

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "df -h"
