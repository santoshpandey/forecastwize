from __future__ import annotations

import pytest
from app.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api

client = TestClient(app)


def test_health_returns_typed_ok_payload() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "forecastwize"
    assert body["version"] == "0.1.0"
    assert body["environment"] in {"development", "production"}
    assert isinstance(body["timestamp"], str)
    assert "T" in body["timestamp"]
    assert body["timestamp"].endswith("Z")
    assert body["llm_configured"] is False
    assert set(body.keys()) == {
        "status",
        "service",
        "version",
        "environment",
        "timestamp",
        "llm_configured",
    }


def test_unknown_path_returns_http_404() -> None:
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
