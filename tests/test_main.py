from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

MOCK_CONTEXT = {"pwd": "/test/dir", "shell": "bash"}
MOCK_THREAD_ID = "test-thread"


@patch("backend.main.generateCommand")
def test_queryEndpoint_returnsGeneratedCommand(mockGenerateCommand):
    """Verify the endpoint packages the generator's output into the expected response shape."""
    mockGenerateCommand.return_value = "ls -la"

    response = client.post("/query", json={
        "query": "list files",
        "context": MOCK_CONTEXT,
        "threadId": MOCK_THREAD_ID,
        "osInfo": "",
        "isQuestion": False,
    })

    assert response.status_code == 200
    assert response.json() == {"command": "ls -la", "isQuestion": False}


@patch("backend.main.generateCommand")
def test_queryEndpoint_forwardsAllFieldsToGenerator(mockGenerateCommand):
    """Verify the endpoint passes query, context, threadId, osInfo, and isQuestion to the generator unchanged."""
    mockGenerateCommand.return_value = "uptime"

    client.post("/query", json={
        "query": "show system uptime",
        "context": MOCK_CONTEXT,
        "threadId": MOCK_THREAD_ID,
        "osInfo": "Linux 5.15 x86_64 / Ubuntu 22.04",
        "isQuestion": False,
    })

    mockGenerateCommand.assert_called_once_with(
        "show system uptime",
        MOCK_CONTEXT,
        "test-thread",
        "Linux 5.15 x86_64 / Ubuntu 22.04",
        False,
    )


@patch("backend.main.generateCommand")
def test_queryEndpoint_returns422WhenValidatorRejects(mockGenerateCommand):
    """Verify the endpoint returns HTTP 422 when the generator raises a validation error."""
    mockGenerateCommand.side_effect = ValueError("Command rejected by validator: Deletes the entire filesystem.")

    response = client.post("/query", json={
        "query": "delete everything",
        "context": MOCK_CONTEXT,
        "threadId": MOCK_THREAD_ID,
    })

    assert response.status_code == 422
    assert "Deletes the entire filesystem." in response.json()["detail"]


@patch("backend.main.generateCommand")
def test_queryEndpoint_returnsExplanationForQuestionQuery(mockGenerateCommand):
    """Verify the endpoint returns the explainer text with isQuestion=True for question queries."""
    mockGenerateCommand.return_value = "Use `ls` to list the contents of a directory."

    response = client.post("/query", json={
        "query": "what command lists files?",
        "context": MOCK_CONTEXT,
        "threadId": MOCK_THREAD_ID,
        "osInfo": "",
        "isQuestion": True,
    })

    assert response.status_code == 200
    assert response.json() == {
        "command": "Use `ls` to list the contents of a directory.",
        "isQuestion": True,
    }


@patch("backend.main.generateCommand")
def test_queryEndpoint_usesDefaultsForOptionalFields(mockGenerateCommand):
    """Verify that osInfo and isQuestion default to empty string and False when omitted from payload."""
    mockGenerateCommand.return_value = "pwd"

    client.post("/query", json={
        "query": "show current directory",
        "context": MOCK_CONTEXT,
        "threadId": MOCK_THREAD_ID,
    })

    mockGenerateCommand.assert_called_once_with(
        "show current directory",
        MOCK_CONTEXT,
        "test-thread",
        "",
        False,
    )
