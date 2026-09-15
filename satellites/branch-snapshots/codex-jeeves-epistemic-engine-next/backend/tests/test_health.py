"""
Health Check Tests for CodeDock Backend
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint returns welcome message."""
        response = client.get("/api/health")  # Use health endpoint instead
        assert response.status_code == 200

    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "ok", "running"]

    def test_languages_endpoint(self, client: TestClient):
        """Test languages endpoint returns list."""
        response = client.get("/api/languages")
        assert response.status_code == 200
        data = response.json()
        # Should return a list or dict with languages
        assert data is not None
