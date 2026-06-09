import pytest
from unittest.mock import MagicMock, patch
from backend.generator import generateCommand

MOCK_CONTEXT = {"pwd": "/test/dir", "shell": "bash"}
MOCK_THREAD_ID = "test-thread"


def buildMockResponse(text: str) -> MagicMock:
    """Construct a mock mirroring the shape of an OpenAI chat completion response."""
    mockMessage = MagicMock()
    mockMessage.content = text
    mockChoice = MagicMock()
    mockChoice.message = mockMessage
    mockResponse = MagicMock()
    mockResponse.choices = [mockChoice]
    return mockResponse


@patch("backend.generator.getRelevantContext", return_value="")
@patch("backend.generator.buildClient")
def test_fullGraph_returnsCommandWhenValidatorApproves(mockBuildClient, mockGetRelevantContext):
    """Verify the full pipeline returns the command string on a SAFE verdict."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("ls -la")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("SAFE")

    # side_effect supplies a different client per call: first to generatorNode, second to validatorNode.
    # retrievalNode uses getRelevantContext (mocked above), not buildClient, so the count is unchanged.
    mockBuildClient.side_effect = [generatorClient, validatorClient]

    result = generateCommand("list all files", MOCK_CONTEXT, MOCK_THREAD_ID)

    assert result == "ls -la"


@patch("backend.generator.getRelevantContext", return_value="")
@patch("backend.generator.buildClient")
def test_fullGraph_raisesValueErrorWhenValidatorRejects(mockBuildClient, mockGetRelevantContext):
    """Verify the full pipeline raises ValueError when the validator returns UNSAFE."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("rm -rf /")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("UNSAFE: Deletes the entire filesystem.")

    mockBuildClient.side_effect = [generatorClient, validatorClient]

    with pytest.raises(ValueError, match="Deletes the entire filesystem."):
        generateCommand("delete everything", MOCK_CONTEXT, MOCK_THREAD_ID)


@patch("backend.generator.getRelevantContext", return_value="")
@patch("backend.generator.buildClient")
def test_fullGraph_generatorOutputIsPassedToValidator(mockBuildClient, mockGetRelevantContext):
    """Verify the command produced by the generator is exactly what the validator receives."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("du -sh *")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("SAFE")

    mockBuildClient.side_effect = [generatorClient, validatorClient]

    generateCommand("show size of each item in current directory", MOCK_CONTEXT, MOCK_THREAD_ID)

    validatorCallArgs = validatorClient.chat.completions.create.call_args
    messages = validatorCallArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "du -sh *"


@patch("backend.generator.getRelevantContext", return_value="Project uses Python 3.12 with a venv.")
@patch("backend.generator.buildClient")
def test_fullGraph_knowledgeBaseIsInjectedIntoGeneratorPrompt(mockBuildClient, mockGetRelevantContext):
    """Verify that RAG context from retrievalNode reaches the generator's system message."""
    generatorClient = MagicMock()
    generatorClient.chat.completions.create.return_value = buildMockResponse("python3 --version")

    validatorClient = MagicMock()
    validatorClient.chat.completions.create.return_value = buildMockResponse("SAFE")

    mockBuildClient.side_effect = [generatorClient, validatorClient]

    generateCommand("check python version", MOCK_CONTEXT, MOCK_THREAD_ID)

    generatorCallArgs = generatorClient.chat.completions.create.call_args
    messages = generatorCallArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "Project uses Python 3.12 with a venv." in systemMessage["content"]


@patch("backend.generator.getRelevantContext", return_value="")
@patch("backend.generator.buildClient")
def test_fullGraph_returnsResponseForQuestionQuery(mockBuildClient, mockGetRelevantContext):
    """Verify the question path returns the explainer's response and bypasses the validator."""
    explainerClient = MagicMock()
    explainerClient.chat.completions.create.return_value = buildMockResponse("Use `ls` to list files.")
    # Question path calls buildClient once (explainerNode only — generatorNode and validatorNode are skipped).
    mockBuildClient.return_value = explainerClient

    result = generateCommand("what command lists files?", MOCK_CONTEXT, "question-thread", isQuestion=True)

    assert result == "Use `ls` to list files."
