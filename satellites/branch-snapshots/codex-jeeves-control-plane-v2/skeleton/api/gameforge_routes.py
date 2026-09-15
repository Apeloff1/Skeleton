"""
Skeleton API — GameForge route handlers

/gameforge/run      — full intake → blueprint → pipelines generation
/gameforge/intake   — questionnaire answers → structured intake only
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from skeleton.api.hmac_seal import require_seal
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.server import get_state

router = APIRouter()
_idempotency = IdempotencyGuard()


def _state():
    return get_state()


@router.post("/gameforge/intake")
async def gameforge_intake(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Process questionnaire answers into a structured intake result."""
    from skeleton.pipelines import GameForge

    forge = GameForge(genesis=state.genesis, bus=state.genesis.bus if state.genesis else None)
    answers = request.get("answers", request)
    result = forge.intake(answers)
    return {"intake": result, "status": "processed"}


@router.post("/gameforge/run")
async def gameforge_run(http_request: Request, request: Dict[str, Any], state=Depends(_state), attester: str = Depends(require_seal)) -> Dict[str, Any]:
    """Run the full game generation pipeline (HMAC sealed, idempotent)."""
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]

    from skeleton.pipelines import GameForge

    forge = GameForge(genesis=state.genesis, bus=state.genesis.bus if state.genesis else None)
    spec = forge.run(
        request.get("answers", {}),
        title=request.get("title"),
        target=request.get("target", "json"),
        repair=bool(request.get("repair", False)),
    )
    response = {"game": spec.to_dict(), "status": "generated"}
    _idempotency.remember(dict(http_request.headers), response)
    return response
