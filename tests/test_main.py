from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_query_endpoint_returns_command():
    response = client.post("/query", json={"query": "list files"})
    assert response.status_code == 200
    assert "command" in response.json()
