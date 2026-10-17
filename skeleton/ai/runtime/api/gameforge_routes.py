"""Unmounted GameForge compatibility handlers.

``create_app`` is the only HTTP entry and does not include this router.
``POST /gameforge/run`` delegates to ``build_playable_game``, the same
executor as ``POST /api/v1/game/build``. ``POST /gameforge/intake`` remains
so existing intake callers and sidecar audits keep a module to import.
Delete this module only after those imports are gone.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.command_routes import router as command_router
from skeleton.api.hmac_seal import require_seal
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
    attester: str = Depends(require_seal),
) -> Dict[str, Any]:
    """Delegate to the playable builder. This router is not mounted."""
    del state, attester
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.forge.game_builder import build_playable_game, public_payload
    from skeleton.forge.playtest import normalise_mode

    brief = str(request.get("brief") or request.get("vision") or "").strip()
    if not brief:
        raise HTTPException(status_code=422, detail="brief is required")
    try:
        mode = normalise_mode(str(request.get("playtest") or "off"))
        rounds = request.get("max_rounds", 3)
        if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 3:
            raise ValueError("max_rounds must be an integer from 1 to 3")
        result = build_playable_game(brief, playtest_mode=mode, max_rounds=rounds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response = public_payload(result, include_files=bool(request.get("include_files", False)))
    _idempotency.remember(dict(http_request.headers), response)
    return response
