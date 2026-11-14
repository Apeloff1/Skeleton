"""Only explicitly typed 503 responses survive the public error boundary."""
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from core.http_errors import (
    PublicHealthUnavailable, PublicUnavailableError, PublicUnavailableResponse,
    install_public_error_handlers,
)
from core.public_exception_route import PublicExceptionRoute


@pytest.fixture
def client():
    app = FastAPI()
    install_public_error_handlers(app)
    router = APIRouter(route_class=PublicExceptionRoute)

    @router.get("/raw")
    def raw():
        return JSONResponse(
            status_code=503,
            content={"code": "marketplace_release_unavailable", "error": "PRIVATE_CANARY"},
            headers={"X-Debug": "PRIVATE_CANARY", "Set-Cookie": "secret=PRIVATE_CANARY"},
        )

    @router.get("/raw-exception")
    def raw_exception():
        raise HTTPException(503, {"code": "artifact_owner_unavailable", "path": "/private/secret"})

    @router.get("/typed")
    def typed():
        return PublicUnavailableResponse("marketplace_release_unavailable")

    @router.get("/unknown")
    def unknown():
        return PublicUnavailableResponse("PRIVATE_CANARY")

    @router.get("/model")
    def model():
        raise PublicUnavailableError("project_model_execution_unconfirmed",
                                     request_key="engine-chat:" + "c" * 64)

    @router.get("/bad-key")
    def bad_key():
        raise PublicUnavailableError("project_model_execution_unconfirmed",
                                     request_key="engine-chat:PRIVATE_CANARY")

    @router.get("/health")
    def health():
        return PublicHealthUnavailable({
            "status": "not_ready",
            "checks": {
                "mongo": {"ok": False, "error": "probe_failed", "path": "/private/secret",
                          "note": "PRIVATE_CANARY"},
                "vault_galaxy": {"ok": True, "path": "/private/secret"},
                "PRIVATE_CANARY": {"ok": True},
            },
        })

    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/raw", "/raw-exception", "/unknown"])
def test_generic_or_unknown_failure_remains_fully_redacted(client, path):
    response = client.get(path)
    assert response.status_code == 503
    assert response.json() == {"detail": "internal server error"}
    assert "PRIVATE_CANARY" not in str(response.headers)
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"


def test_typed_release_denial_is_fixed_and_actionable(client):
    response = client.get("/typed")
    assert response.status_code == 503
    assert response.json()["code"] == "marketplace_release_unavailable"
    assert "gameplay and buyer access" in response.json()["error"]


def test_retry_key_is_opaque_and_strictly_validated(client):
    good = client.get("/model")
    assert good.status_code == 503
    assert good.json()["detail"]["retry_same_request"] is True
    assert good.json()["detail"]["engine_request_key"] == "engine-chat:" + "c" * 64
    bad = client.get("/bad-key")
    assert bad.json()["detail"]["engine_request_key"] is None
    assert "PRIVATE_CANARY" not in bad.text


def test_health_exposes_state_but_not_arbitrary_diagnostics(client):
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"mongo": {"ok": False, "error": "probe_failed"},
                   "vault_galaxy": {"ok": True}},
    }
    assert "/private/secret" not in response.text
    assert "PRIVATE_CANARY" not in response.text
