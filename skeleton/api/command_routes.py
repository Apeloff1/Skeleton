"""API transport for the shared application command contracts."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from skeleton.api.server import get_state
from skeleton.application import build_runtime_command_service, parity_matrix

router = APIRouter()


def _state():
    return get_state()


@router.get("/commands/contracts")
async def command_contracts() -> Dict[str, Any]:
    """Return the machine-readable API/CLI feature-parity contract."""

    return parity_matrix()


@router.post("/commands/execute/{command}")
async def execute_command(command: str, request: Dict[str, Any], state=Depends(_state)):
    """Execute a command through the same service contract used by the CLI."""

    result = build_runtime_command_service(state).execute(command, request)
    payload = result.to_payload()
    if result.ok:
        return payload
    return JSONResponse(status_code=result.http_status, content=payload)
