from unittest.mock import MagicMock, patch
from backend.generator import explainerNode, EXPLAINER_PROMPT

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


def buildState(query: str = "what does ls do?", pastCommands: list = None) -> dict:
    """Return a fully-populated AgentState dict representing a question query."""
    return {
        "query": query,
        "context": MOCK_CONTEXT,
        "knowledgeBase": "",
        "osInfo": "",
        "isQuestion": True,
        "command": "",
        "response": "",
        "isValid": False,
        "rejectionReason": "",
        "pastCommands": pastCommands if pastCommands is not None else [],
    }


@patch("backend.generator.buildClient")
def test_explainerNode_populatesResponseFromModel(mockBuildClient):
    """Verify the node writes the model's answer into the response state key."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("`ls` lists directory contents.")
    mockBuildClient.return_value = mockClient

    result = explainerNode(buildState("what does ls do?"))

    assert result == {"response": "`ls` lists directory contents.", "isValid": True}


@patch("backend.generator.buildClient")
def test_explainerNode_stripsWhitespace(mockBuildClient):
    """Verify that leading/trailing whitespace in the model response is stripped."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("  Use `pwd` to print the path.  ")
    mockBuildClient.return_value = mockClient

    result = explainerNode(buildState("how do I see my current directory?"))

    assert result["response"] == "Use `pwd` to print the path."


@patch("backend.generator.buildClient")
def test_explainerNode_setsIsValidTrue(mockBuildClient):
    """Verify the node always marks the state as valid so generateCommand skips the validator check."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("Use `grep` to search file contents.")
    mockBuildClient.return_value = mockClient

    result = explainerNode(buildState("how do I search in files?"))

    assert result["isValid"] is True


@patch("backend.generator.buildClient")
def test_explainerNode_usesCorrectSystemPrompt(mockBuildClient):
    """Verify the node's system message contains EXPLAINER_PROMPT (after the context header)."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("Answer.")
    mockBuildClient.return_value = mockClient

    explainerNode(buildState("what is a symlink?"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert EXPLAINER_PROMPT in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_explainerNode_forwardsQueryAsUserMessage(mockBuildClient):
    """Verify the user's question is forwarded in the user-role message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("Answer.")
    mockBuildClient.return_value = mockClient

    explainerNode(buildState("what is the difference between cp and mv?"))

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    userMessage = next(m for m in messages if m["role"] == "user")
    assert userMessage["content"] == "what is the difference between cp and mv?"


@patch("backend.generator.buildClient")
def test_explainerNode_injectsOsInfoIntoSystemMessage(mockBuildClient):
    """Verify that a non-empty osInfo string appears in the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("Answer.")
    mockBuildClient.return_value = mockClient

    state = buildState("what kernel am I running?")
    state["osInfo"] = "Linux 5.15.0 x86_64 / Ubuntu 22.04.3 LTS"
    explainerNode(state)

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "Linux 5.15.0 x86_64 / Ubuntu 22.04.3 LTS" in systemMessage["content"]


@patch("backend.generator.buildClient")
def test_explainerNode_injectsKnowledgeBaseIntoSystemMessage(mockBuildClient):
    """Verify that a non-empty knowledgeBase is injected into the system message."""
    mockClient = MagicMock()
    mockClient.chat.completions.create.return_value = buildMockResponse("Answer.")
    mockBuildClient.return_value = mockClient

    state = buildState("what aliases do I have?")
    state["knowledgeBase"] = "Custom alias: ll means ls -la --color=auto"
    explainerNode(state)

    callArgs = mockClient.chat.completions.create.call_args
    messages = callArgs.kwargs["messages"]
    systemMessage = next(m for m in messages if m["role"] == "system")
    assert "Custom alias: ll means ls -la --color=auto" in systemMessage["content"]
