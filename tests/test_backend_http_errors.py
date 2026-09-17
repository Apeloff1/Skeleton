"""Hermetic backend public-error regressions that do not import server.py."""
from __future__ import annotations

import asyncio
import ast
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.http_errors import (  # noqa: E402
    PUBLIC_INTERNAL_ERROR,
    install_public_error_handlers,
    internal_http_error,
    redact_client_payload,
    redact_client_text,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_FILES = [
    REPO_ROOT / "backend" / "routes" / "jeeves_tutor.py",
    REPO_ROOT / "backend" / "routes" / "npc_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "music_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "image_generation.py",
    REPO_ROOT / "backend" / "routes" / "export_github.py",
    REPO_ROOT / "backend" / "routes" / "gameforge_workflow.py",
    REPO_ROOT / "backend" / "routes" / "omega_conductor.py",
]

_PRIVATE = "private-detail-must-not-leak-7f31"


def _is_exception_handler(handler: ast.ExceptHandler) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def _http_exception_calls(node: ast.AST):
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "HTTPException"
        ):
            yield child


def _references_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.Name)
        and isinstance(child.ctx, ast.Load)
        and child.id == name
        for child in ast.walk(node)
    )


def _broad_failure_http_leaks(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    leaks: list[int] = []
    for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
        if not _is_exception_handler(handler) or not handler.name:
            continue
        for statement in handler.body:
            for call in _http_exception_calls(statement):
                if _references_name(call, handler.name):
                    leaks.append(call.lineno)
    return leaks


@pytest.mark.parametrize("path", ROUTE_FILES, ids=lambda path: path.name)
def test_converted_routes_do_not_leak_caught_exceptions(path: Path) -> None:
    leaks = _broad_failure_http_leaks(path)
    assert leaks == [], f"{path.name} exposes caught exception data in HTTP responses at lines {leaks}"


def test_internal_http_error_is_stable_and_typed() -> None:
    exc = internal_http_error("Jeeves request failed", RuntimeError(_PRIVATE))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 500
    assert exc.detail == "Jeeves request failed"
    assert _PRIVATE not in str(exc.detail)


def test_unhandled_exception_handler_redacts_detail() -> None:
    app = FastAPI()
    before = app.exception_handlers.get(StarletteHTTPException)
    install_public_error_handlers(app)
    assert app.exception_handlers.get(StarletteHTTPException) is before
    handler = app.exception_handlers[Exception]
    response = asyncio.run(handler(None, RuntimeError(_PRIVATE)))
    assert response.status_code == 500
    payload = response.body.decode("utf-8")
    assert PUBLIC_INTERNAL_ERROR in payload
    assert _PRIVATE not in payload


def test_redact_client_text_strips_credentials() -> None:
    rendered = redact_client_text(
        "authorization=Bearer abc.def token=super-secret password=hunter2"
    )
    assert "abc.def" not in rendered
    assert "super-secret" not in rendered
    assert "hunter2" not in rendered
    assert rendered.count("[REDACTED]") >= 2


def test_redact_client_payload_is_bounded() -> None:
    payload = {"token": "abc", "nested": {"password": "x", "ok": "fine"}}
    redacted = redact_client_payload(payload)
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["ok"] == "fine"
