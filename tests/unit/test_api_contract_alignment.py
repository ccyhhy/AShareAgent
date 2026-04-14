from fastapi.testclient import TestClient

from backend.main import app


def test_api_agents_returns_api_response_wrapper() -> None:
    with TestClient(app) as client:
        response = client.get("/api/agents/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)
    assert "message" in payload


def test_logs_endpoint_remains_raw_list() -> None:
    with TestClient(app) as client:
        response = client.get("/logs/?limit=1")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_runs_endpoint_remains_raw_list() -> None:
    with TestClient(app) as client:
        response = client.get("/runs/?limit=1")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_monitor_health_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/monitor/health")

    assert response.status_code == 401
