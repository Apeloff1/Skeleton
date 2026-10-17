"""Seal-gated GameForge sidecar.

Production GameForge HTTP is the charter-gated handlers on
``skeleton.api.routes`` (``POST /api/v1/gameforge/run`` and
``POST /api/v1/gameforge/intake``), mounted by ``create_app``.

This module keeps the older seal-gated handlers for direct tests and for
callers that still import them. It does not include the command router.
Nesting that router imported ``skeleton.api.server`` at module scope and
made a cycle whenever the server imported this module. Command routes mount
on their own.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.hmac_seal import require_seal
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.application import build_runtime_command_service

CANONICAL_HTTP_SURFACE = "skeleton.api.routes"

router = APIRouter()
_idempotency = IdempotencyGuard()


def _state():
    from skeleton.api.server import get_state

    return get_state()


@router.post("/gameforge/intake")
async def gameforge_intake(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Process questionnaire answers into a structured intake result."""
    from skeleton.application.command_contracts import CommandError, require_mapping
    from skeleton.pipelines import GameForge

    try:
        answers = require_mapping(request, "answers", {}, optional=False) or {}
    except CommandError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc

    forge = GameForge(genesis=state.genesis, bus=state.genesis.bus if state.genesis else None)
    result = forge.intake(answers)
    return {"intake": result, "status": "processed"}


@router.post("/gameforge/run")
async def gameforge_run(
    http_request: Request,
    request: Dict[str, Any],
    state=Depends(_state),
    attester: str = Depends(require_seal),
) -> Dict[str, Any]:
    """Run GameForge through the shared API/CLI application command service."""
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]

    result = build_runtime_command_service(state).execute("run", request)
    if not result.ok:
        error = result.error
        raise HTTPException(
            status_code=result.http_status,
            detail=error.to_dict() if error is not None else {"code": "internal_error", "message": "run failed"},
        )

    response = dict(result.data)
    _idempotency.remember(dict(http_request.headers), response)
    return response
