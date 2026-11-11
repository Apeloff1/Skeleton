"""Regression contract for all 125 historically reported exception exposures.

This proves the HTTP exception custody boundary covers the 49 source modules
identified in the versioned CodeQL snapshot. It is NOT evidence that any
GitHub CodeQL alert has closed: fresh exact-main analysis remains mandatory.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from core.public_exception_route import PublicExceptionRoute

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/security/codeql-open-151-lineage-2026-11-11.json"
PROJECT = ROOT / "backend/routes/playable_access.py"
CONTROL = "backend/gameforge/api/control.py"
GAMEFORGE_BUILD = "backend/routes/gameforge_build.py"


def _exposure_sources() -> tuple[list[str], list[int]]:
    snapshot = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert snapshot["observed_code_scanning_alerts"] == 151
    findings = [
        entry for entry in snapshot["findings"]
        if entry["rule_id"] == "py/stack-trace-exposure"
    ]
    return sorted({entry["path"] for entry in findings}), [entry["number"] for entry in findings]


def test_all_49_codeql_exception_origins_have_runtime_error_custody():
    paths, alerts = _exposure_sources()
    assert len(paths) == 49
    assert len(alerts) == len(set(alerts)) == 125
    shared = PROJECT.read_text(encoding="utf-8")
    assert "class _PrivateProjectRoute(PublicExceptionRoute):" in shared
    assert 'kwargs.setdefault("route_class", _PrivateProjectRoute)' in shared

    uncovered = []
    guarded = 0
    for relative in paths:
        source_path = ROOT / relative
        source = source_path.read_text(encoding="utf-8")
        # Files containing unguarded top-level FastAPI route handlers are
        # handled separately from the APIRouter and project-router families.
        if relative == CONTROL:
            if "install_public_error_handlers(app)" not in source:
                uncovered.append(relative)
            else:
                guarded += 1
            continue
        if relative == GAMEFORGE_BUILD:
            if "route_class=_PrivateProjectRoute" not in source:
                uncovered.append(relative)
            else:
                guarded += 1
            continue
        if re.search(r"\brouter\s*=\s*project_router\(", source):
            guarded += 1
            continue
        if "route_class=PublicExceptionRoute" in source:
            assert "from core.public_exception_route import PublicExceptionRoute" in source
            guarded += 1
            continue
        uncovered.append(relative)

    assert guarded == len(paths), f"CodeQL-identified routes lacking 500 redaction: {uncovered}"
    assert not uncovered


def test_runtime_boundary_never_leaks_exception_messages_or_stack_traces():
    app = FastAPI()
    router = APIRouter(route_class=PublicExceptionRoute)
    secret = "customer-session-token=cannot-be-exposed-458e"

    @router.get("/crash")
    async def crash():
        raise RuntimeError(secret + "\nprivate/file/path")

    @router.get("/public")
    async def public():
        raise HTTPException(409, "expected conflict")

    class Body(BaseModel):
        amount: int

    @router.post("/validate")
    async def validated(body: Body):
        return {"amount": body.amount}

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        crash_result = client.get("/crash")
        public_result = client.get("/public")
        validation = client.post("/validate", json={"amount": "not-an-int"})
    assert crash_result.status_code == 500
    assert crash_result.json() == {"detail": "internal server error"}
    assert secret not in crash_result.text
    assert "private/file/path" not in crash_result.text
    assert public_result.status_code == 409
    assert public_result.json() == {"detail": "expected conflict"}
    assert validation.status_code == 422
    assert validation.json()["detail"]


@pytest.mark.parametrize("module", [
    "backend/routes/code_intelligence.py",
    "backend/routes/ai_toolkit_enhanced.py",
    "backend/routes/collaboration.py",
    "backend/gameforge/api/math_api.py",
    "backend/routes/agent_knowledge.py",
    "backend/routes/galaxy_studio.py",
    "backend/routes/gameforge_studio.py",
    "backend/gameforge/api/scim.py",
])
def test_high_volume_codeql_route_modules_have_explicit_guard(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    # Catch bypasses in review instead of trusting a runtime stack-trace test
    # that covers only one synthetic route.
    assert re.search(r"\brouter\s*=\s*APIRouter\(route_class=PublicExceptionRoute,", source)
    assert "from core.public_exception_route import PublicExceptionRoute" in source


def test_guarded_modules_parse_and_never_overwrite_public_http_error_contract():
    paths, _ = _exposure_sources()
    for relative in paths:
        ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
    source = (ROOT / "backend/core/public_exception_route.py").read_text(encoding="utf-8")
    assert "except (StarletteHTTPException, RequestValidationError)" in source
    assert "raise StarletteHTTPException(" in source
    assert "status_code=500, detail=PUBLIC_INTERNAL_ERROR" in source
