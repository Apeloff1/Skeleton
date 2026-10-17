"""Unmounted GameForge compatibility handlers.

``create_app`` is the only HTTP entry and does not include this router.
``POST /gameforge/run`` re-exports the mounted adapter in
``skeleton.api.routes`` (``build_playable_game``) and uses the same
``require_charter("forge", "run")`` gate. ``POST /gameforge/intake`` remains
so existing intake callers and sidecar audits keep a module to import.
Delete this module only after those imports are gone.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.charter_gate import require_charter
from skeleton.api.command_routes import router as command_router
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.server import get_state

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
    attester: str = Depends(require_charter("forge", "run")),
) -> Dict[str, Any]:
    """Re-export the mounted ``/gameforge/run`` adapter. This router is not mounted."""
    del attester
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.api.routes import run_gameforge_adapter
    from starlette.concurrency import run_in_threadpool

    try:
        response = await run_in_threadpool(run_gameforge_adapter, request, state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _idempotency.remember(dict(http_request.headers), response)
    return response
