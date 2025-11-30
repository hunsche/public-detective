"""Tests for the web main module."""

from fastapi.testclient import TestClient
from public_detective.web.main import app


def test_health_check() -> None:
    """Tests the health check endpoint."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
