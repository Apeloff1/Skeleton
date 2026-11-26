"""RFC 9457 problem+json negotiation on the public error handlers."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.http_errors import (  # noqa: E402
    PROBLEM_JSON,
    PUBLIC_INTERNAL_ERROR,
    PublicUnavailableError,
    install_public_error_handlers,
    problem_document,
)
from core.observability import ObservabilityMiddleware  # noqa: E402

ACCEPT = {"Accept": "application/problem+json, application/json;q=0.5"}


class Body(BaseModel):
    count: int


def _app() -> TestClient:
    app = FastAPI()
    install_public_error_handlers(app)
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="project not found")

    @app.get("/leak")
    async def leak():
        raise HTTPException(status_code=502, detail="upstream token=sk-live-123",
                            headers={"X-Upstream": "secret"})

    @app.get("/crash")
    async def crash():
        raise RuntimeError("password=hunter2")

    @app.get("/unavailable")
    async def unavailable():
        raise PublicUnavailableError("jeeves_unavailable")

    @app.post("/validate")
    async def validate(body: Body):
        return body

    return TestClient(app, raise_server_exceptions=False)


def test_legacy_shape_unchanged_without_negotiation():
    client = _app()
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "project not found"}


def test_4xx_problem_document():
    resp = _app().get("/missing", headers=ACCEPT)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
    body = resp.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["detail"] == "project not found"
    assert body["instance"] == "/missing"
    assert len(body["trace_id"]) == 32


def test_5xx_problem_document_stays_redacted():
    client = _app()
    resp = client.get("/leak", headers=ACCEPT)
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"] == PUBLIC_INTERNAL_ERROR
    assert "sk-live" not in resp.text
    assert "x-upstream" not in {k.lower() for k in resp.headers}
    assert resp.headers["cache-control"] == "no-store"

    crash = client.get("/crash", headers=ACCEPT)
    assert crash.status_code == 500
    assert crash.headers["content-type"].startswith(PROBLEM_JSON)
    assert "hunter2" not in crash.text
    assert crash.json()["title"] == "Internal Server Error"


def test_typed_unavailable_keeps_public_code():
    resp = _app().get("/unavailable", headers=ACCEPT)
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == 503
    assert body["title"] == "Service Unavailable"


def test_validation_errors_become_errors_extension():
    client = _app()
    legacy = client.post("/validate", json={"count": "x"})
    assert legacy.status_code == 422 and isinstance(legacy.json()["detail"], list)
    resp = client.post("/validate", json={"count": "x"}, headers=ACCEPT)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "request validation failed"
    assert isinstance(body["errors"], list) and body["errors"]
    assert body["title"] == "Unprocessable Content"


def test_problem_document_bounds_and_redaction():
    body = problem_document(400, "bad token=abc123 " + "x" * 2000, instance="/a",
                            request_id="r" * 500, trace_id="not-hex")
    assert "abc123" not in body["detail"]
    assert len(body["detail"]) <= 512
    assert "request_id" not in body and "trace_id" not in body
