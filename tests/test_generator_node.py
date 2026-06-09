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


def buildState(query: str = "list all files", command: str = "", pastCommands: list = None) -> dict:
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


@patch("backend.generator.buildClient")
def test_generatorNode_injectsOsInfoIntoSystemMessage(mockBuildClient):
    """Verify that a non-empty osInfo string appears in the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("uname -a")
    mockBuildClient.return_value = mockClient

    state = buildState("show os version")
    state["osInfo"] = "Linux 5.15.0 x86_64 / Ubuntu 22.04.3 LTS"
    generatorNode(state)

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "Linux 5.15.0 x86_64 / Ubuntu 22.04.3 LTS" in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_generatorNode_injectsPastCommandsIntoSystemMessage(mockBuildClient):
    """Verify that prior session commands from state are injected into the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ls -la")
    mockBuildClient.return_value = mockClient

    mockHistory = [
        "User: show disk usage -> AI: df -h",
        "User: show system uptime -> AI: uptime",
    ]
    generatorNode(buildState("list files", pastCommands=mockHistory))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "User: show disk usage -> AI: df -h" in systemMessage["content"]
    assert "User: show system uptime -> AI: uptime" in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_generatorNode_injectsKnowledgeBaseIntoSystemMessage(mockBuildClient):
    """Verify that a non-empty knowledgeBase is injected into the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ll")
    mockBuildClient.return_value = mockClient

    stateWithKnowledge = buildState("list files")
    stateWithKnowledge["knowledgeBase"] = "Custom alias: ll means ls -la --color=auto"

    generatorNode(stateWithKnowledge)

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "Custom alias: ll means ls -la --color=auto" in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_generatorNode_omitsKnowledgeBaseSectionWhenEmpty(mockBuildClient):
    """Verify that an empty knowledgeBase does not add the RAG section to the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("ls")
    mockBuildClient.return_value = mockClient

    generatorNode(buildState("list files"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "Proprietary Local Knowledge" not in systemMessage["content"]
