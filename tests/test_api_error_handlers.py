"""Fail-closed HTTP error envelopes for the Skeleton API."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skeleton.api.errors import (  # noqa: E402
    INTERNAL_ERROR_MESSAGE,
    install_error_handlers,
    map_error,
    skeleton_error_handler,
)
from skeleton.api.server import skeleton_error_handler as exported_handler  # noqa: E402
from skeleton.kernel.errors import CapabilityNotFoundError, SkeletonError  # noqa: E402


_PRIVATE = "private-detail-must-not-leak-7f31"


def test_skeleton_error_handler_is_exported_from_server() -> None:
    assert exported_handler is skeleton_error_handler


def test_map_error_redacts_client_error_secrets() -> None:
    err = CapabilityNotFoundError(
        "missing capability",
        context={"authorization": "Bearer super-secret", "name": "npc"},
    )
    body = map_error(err).to_dict()["error"]
    assert body["code"] == "KRN.CAPABILITY_NOT_FOUND"
    assert body["message"] == "missing capability"
    assert body["context"]["authorization"] == "[REDACTED]"
    assert body["context"]["name"] == "npc"
    assert "super-secret" not in repr(body)


def test_map_error_hides_server_error_message_and_context() -> None:
    err = SkeletonError(_PRIVATE, context={"token": "abc123"})
    mapped = map_error(err)
    assert mapped.status == 500
    body = mapped.to_dict()["error"]
    assert body["message"] == INTERNAL_ERROR_MESSAGE
    assert body["context"] == {}
    assert _PRIVATE not in repr(body)
    assert "abc123" not in repr(body)


def test_unhandled_exception_is_redacted() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(_PRIVATE)

    @app.get("/http")
    def http() -> None:
        raise HTTPException(status_code=503, detail="seal unavailable")

    client = TestClient(app, raise_server_exceptions=False)
    leaked = client.get("/boom")
    assert leaked.status_code == 500
    assert leaked.json()["error"]["message"] == INTERNAL_ERROR_MESSAGE
    assert _PRIVATE not in leaked.text

    known = client.get("/http")
    assert known.status_code == 503
    assert known.json() == {"detail": "seal unavailable"}


def test_lattice_handler_uses_public_payload() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise CapabilityNotFoundError("npc pipeline missing")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/missing")
    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "KRN.CAPABILITY_NOT_FOUND"
    assert body["message"] == "npc pipeline missing"
