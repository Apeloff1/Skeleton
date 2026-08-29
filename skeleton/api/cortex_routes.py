"""Cortex routes — read-only surface over the genesis cortex handle.

Mounted from ``skeleton/api/routes.py`` alongside the other routers. The
cortex itself is the model organism; these endpoints only *inspect* it.
Mutation paths (train/acquire/surpass) stay on the CLI/cockpit until a
serving decision is made (H5 design note in BUILD_PLAN.md).
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from skeleton.api.server import get_state

router = APIRouter()


def _state():
    return get_state()


def _cortex(state: Any) -> Any:
    genesis = state.genesis
    if genesis is None:
        raise HTTPException(status_code=503, detail="genesis not booted")
    cortex = genesis.handles.get("cortex")
    if cortex is None:
        raise HTTPException(status_code=503, detail="cortex not wired")
    return cortex


@router.get("/cortex/status")
async def cortex_status(state=Depends(_state)) -> Dict[str, Any]:
    cortex = _cortex(state)
    status = cortex.status() if hasattr(cortex, "status") else cortex.to_dict()
    return {"cortex": status}


@router.post("/cortex/think")
async def cortex_think(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    cortex = _cortex(state)
    stimulus = str(request.get("stimulus", "")).strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    ctx = {"era": request.get("era", "extraction_now")}
    trace = cortex.think(stimulus, ctx)
    return {"trace": trace.to_dict() if hasattr(trace, "to_dict") else trace}
