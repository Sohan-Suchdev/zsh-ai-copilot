from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


@patch("backend.main.generateCommand")
def test_queryEndpoint_returnsGeneratedCommand(mockGenerateCommand):
    """Verify the endpoint packages the generator's output into the expected response shape."""
    mockGenerateCommand.return_value = "ls -la"

    response = client.post("/query", json={"query": "list files"})

    assert response.status_code == 200
    assert response.json() == {"command": "ls -la"}


@patch("backend.main.generateCommand")
def test_queryEndpoint_forwardsQueryToGenerator(mockGenerateCommand):
    """Verify the endpoint passes the raw query string through to the generator unchanged."""
    mockGenerateCommand.return_value = "uptime"

    client.post("/query", json={"query": "show system uptime"})

    mockGenerateCommand.assert_called_once_with("show system uptime")


@patch("backend.main.generateCommand")
def test_queryEndpoint_returns422WhenValidatorRejects(mockGenerateCommand):
    """Verify the endpoint returns HTTP 422 when the generator raises a validation error."""
    mockGenerateCommand.side_effect = ValueError("Command rejected by validator: Deletes the entire filesystem.")

    response = client.post("/query", json={"query": "delete everything"})

    assert response.status_code == 422
    assert "Deletes the entire filesystem." in response.json()["detail"]
