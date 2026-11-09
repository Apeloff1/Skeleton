"""Configured browser origins reach engine health without weakening authority."""
from fastapi.testclient import TestClient
import pytest

from skeleton.api.server import create_app
from skeleton.config.settings import get_settings


@pytest.mark.parametrize("origin,status,allowed", [
    ("http://127.0.0.1:33000", 200, True),
    ("https://untrusted.example", 400, False),
])
def test_engine_uses_declared_cors_origin_policy(monkeypatch, origin, status, allowed):
    monkeypatch.setenv("SKL_SERVER_CORS_ORIGINS", '["http://127.0.0.1:33000"]')
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        response = client.options("/api/v1/health/live", headers={
            "Origin": origin, "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-request-id",
        })
        assert response.status_code == status
        assert ("access-control-allow-origin" in response.headers) is allowed
        assert response.headers.get("access-control-allow-credentials") != "true"
    finally:
        get_settings.cache_clear()
