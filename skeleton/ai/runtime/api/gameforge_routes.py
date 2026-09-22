"""
Skeleton API — GameForge route handlers

/gameforge/run      — full intake → blueprint → pipelines generation
/gameforge/intake   — questionnaire answers → structured intake only
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.command_routes import router as command_router
from skeleton.api.hmac_seal import require_seal
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.server import get_state
from skeleton.application import build_runtime_command_service

router = APIRouter()
router.include_router(command_router)
_idempotency = IdempotencyGuard()


def _state():
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
