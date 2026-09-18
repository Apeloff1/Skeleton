"""API transport for the shared application command contracts."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from skeleton.api.hmac_seal import require_seal
from skeleton.api.server import get_state
from skeleton.application import (
    build_runtime_command_service,
    command_specs,
    invoke_unified,
    parity_matrix,
)

router = APIRouter()
_AUTH_REQUIRED = {spec.name for spec in command_specs() if spec.auth_required}


def _state():
    return get_state()


@router.get("/commands/contracts")
async def command_contracts() -> Dict[str, Any]:
    """Return the machine-readable API/CLI feature-parity contract."""

    return parity_matrix()


@router.post("/commands/execute/{command}")
async def execute_command(
    command: str,
    request: Dict[str, Any],
    state=Depends(_state),
    x_gf_seal: Optional[str] = Header(default=None, alias="x-gf-seal"),
):
    """Execute a command through the same service contract used by the CLI.

    Commands declared ``auth_required`` in the shared contract must cross the
    same HMAC-seal boundary as the legacy GameForge mutate route. Public
    inspection commands such as status/configuration remain available without
    a seal, preserving the transport-neutral contract while preventing the
    generic dispatcher from becoming an authorization bypass.
    """

    normalized = str(command or "").strip().lower()
    if normalized in _AUTH_REQUIRED:
        require_seal(x_gf_seal)

    result = build_runtime_command_service(state).execute(normalized, request)
    payload = result.to_payload()
    if result.ok:
        return payload
    return JSONResponse(status_code=result.http_status, content=payload)


@router.post("/commands/invoke")
async def invoke_command(
    request: Dict[str, Any],
    state=Depends(_state),
    x_gf_seal: Optional[str] = Header(default=None, alias="x-gf-seal"),
    x_request_id: Optional[str] = Header(default=None, alias="x-request-id"),
):
    """Execute the versioned unified envelope used by the CLI invoke command.

    Authorization follows the same command-family contract as
    ``/commands/execute/{command}``. Correlation is taken from the envelope
    when valid, otherwise from ``X-Request-ID``.
    """

    preview = str((request or {}).get("command") or "").strip().lower()
    if preview in _AUTH_REQUIRED:
        require_seal(x_gf_seal)

    result = invoke_unified(state, request, correlation_id=x_request_id)
    payload = result.to_payload()
    if result.ok:
        return payload
    return JSONResponse(status_code=result.http_status, content=payload)
