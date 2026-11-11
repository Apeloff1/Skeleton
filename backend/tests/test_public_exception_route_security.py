"""Behavioral and source-contract regression for server-error redaction."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from core.public_exception_route import PublicExceptionRoute


def _app() -> FastAPI:
    app = FastAPI()
    router = APIRouter(route_class=PublicExceptionRoute)

    @router.get("/failure")
    async def failure():
        raise RuntimeError("SECRET_ACCESS_TOKEN=do-not-expose /var/private/files")

    @router.get("/known/{code}")
    async def known(code: int):
        if code == 404:
            raise HTTPException(404, "known public error")
        return {"ok": True}

    class Payload(BaseModel):
        count: int

    @router.post("/validated")
    async def validated(payload: Payload):
        return {"value": payload.count}

    app.include_router(router)
    return app


def test_unexpected_error_never_leaks_internal_message():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/failure")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "SECRET_ACCESS_TOKEN" not in response.text
    assert "/var/private" not in response.text


def test_explicit_public_http_errors_are_preserved():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/known/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "known public error"}


def test_request_validation_remains_http_422():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.post("/validated", json={"count": "not-a-number"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"]


def test_legacy_routes_use_fail_closed_error_boundary():
    backend = Path(__file__).resolve().parents[1]
    for filename in (
        "nexus.py", "swarm_planner.py", "swarm_cold_legion.py",
        "storage.py", "text_gamefile.py", "sota_2026.py",
        "gameforge_build.py", "build_pipeline.py",
    ):
        source = (backend / "routes" / filename).read_text(encoding="utf-8")
        assert "PublicExceptionRoute" in source, filename
        assert "route_class=PublicExceptionRoute" in source, filename
