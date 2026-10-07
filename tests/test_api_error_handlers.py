"""Fail-closed HTTP error envelopes for the Skeleton API."""
from __future__ import annotations

import asyncio

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from skeleton.api.errors import (  # noqa: E402
    INTERNAL_ERROR_MESSAGE,
    install_error_handlers,
    map_error,
    skeleton_error_handler,
    unhandled_error_handler,
)
from skeleton.api.server import skeleton_error_handler as exported_handler  # noqa: E402
from skeleton.kernel.errors import CapabilityNotFoundError, SkeletonError  # noqa: E402


_PRIVATE = "private-detail-must-not-leak-7f31"


def test_skeleton_error_handler_is_exported_from_server() -> None:
    assert exported_handler is skeleton_error_handler


def test_public_payload_hides_server_internals() -> None:
    err = SkeletonError("token=super-secret", context={"path": "/tmp/key"})
    payload = err.public_payload()
    assert payload["message"] == INTERNAL_ERROR_MESSAGE
    assert payload["context"] == {}
    assert "super-secret" not in repr(payload)
    assert err.to_dict()["message"] == "token=super-secret"


def test_public_payload_keeps_client_errors() -> None:
    err = CapabilityNotFoundError("npc pipeline missing")
    payload = err.public_payload()
    assert payload["message"] == "npc pipeline missing"
    assert payload["code"] == "KRN.CAPABILITY_NOT_FOUND"


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


def test_unhandled_exception_handler_redacts_detail() -> None:
    response = asyncio.run(unhandled_error_handler(None, RuntimeError(_PRIVATE)))
    assert response.status_code == 500
    assert response.body
    payload = response.body.decode("utf-8")
    assert INTERNAL_ERROR_MESSAGE in payload
    assert _PRIVATE not in payload


def test_lattice_handler_uses_public_payload() -> None:
    err = CapabilityNotFoundError("npc pipeline missing")
    response = asyncio.run(skeleton_error_handler(None, err))
    assert response.status_code == 404
    payload = response.body.decode("utf-8")
    assert "KRN.CAPABILITY_NOT_FOUND" in payload
    assert "npc pipeline missing" in payload


def test_install_preserves_http_exception_handler() -> None:
    app = FastAPI()
    before = app.exception_handlers.get(StarletteHTTPException)
    install_error_handlers(app)
    assert app.exception_handlers.get(StarletteHTTPException) is before
    assert app.exception_handlers[SkeletonError] is skeleton_error_handler
    assert app.exception_handlers[Exception] is unhandled_error_handler
