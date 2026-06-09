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

    response = client.post("/query", json={"query": "list files", "context": MOCK_CONTEXT, "threadId": MOCK_THREAD_ID})

    assert response.status_code == 200
    assert response.json() == {"command": "ls -la"}


@patch("backend.main.generateCommand")
def test_queryEndpoint_forwardsQueryAndContextToGenerator(mockGenerateCommand):
    """Verify the endpoint passes the query, context, and threadId through to the generator unchanged."""
    mockGenerateCommand.return_value = "uptime"

    client.post("/query", json={"query": "show system uptime", "context": MOCK_CONTEXT, "threadId": MOCK_THREAD_ID})

    mockGenerateCommand.assert_called_once_with("show system uptime", MOCK_CONTEXT, "test-thread")


@patch("backend.main.generateCommand")
def test_queryEndpoint_returns422WhenValidatorRejects(mockGenerateCommand):
    """Verify the endpoint returns HTTP 422 when the generator raises a validation error."""
    mockGenerateCommand.side_effect = ValueError("Command rejected by validator: Deletes the entire filesystem.")

    response = client.post("/query", json={"query": "delete everything", "context": MOCK_CONTEXT, "threadId": MOCK_THREAD_ID})

    assert response.status_code == 422
    assert "Deletes the entire filesystem." in response.json()["detail"]
