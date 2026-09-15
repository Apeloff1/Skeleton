"""API transport for the shared application command contracts."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from skeleton.api.hmac_seal import require_seal
from skeleton.api.server import get_state
from skeleton.application import build_runtime_command_service, command_specs, parity_matrix

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
