"""Cortex command deck — inspect AND speak."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from skeleton.api.server import get_state
from skeleton.cortex.deck import CommandDeck

router = APIRouter()
_decks: Dict[int, CommandDeck] = {}


def _state():
    return get_state()


def _neo(state: Any) -> Any:
    genesis = getattr(state, "genesis", None)
    if genesis is not None:
        cortex = (genesis.handles or {}).get("cortex")
        if cortex is not None:
            return cortex
    from skeleton.cortex.live import live_cortex
    return live_cortex()


def _deck(state: Any) -> CommandDeck:
    neo = _neo(state)
    key = id(neo)
    inst = _decks.get(key)
    if inst is None or inst.neo is not neo:
        inst = CommandDeck(neo)
        _decks[key] = inst
    return inst

@router.get("/cortex/failures")
async def cortex_failures(surface: str = "", state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).failures(surface=surface)

@router.get("/cortex/repairs")
async def cortex_repairs(surface: str = "", state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repairs(surface=surface)

@router.get("/cortex/activity")
async def cortex_activity(surface: str = "", kind: str = "", limit: int = 8, state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).activity(surface=surface, kind=kind, limit=limit)

@router.get("/cortex/recurring")
async def cortex_recurring(surface: str = "", state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).recurring(surface=surface)

@router.get("/cortex/policy")
async def cortex_policy(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).policy()

@router.get("/cortex/threshold")
async def cortex_threshold(surface: str = "", state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).threshold(surface=surface)

@router.post("/cortex/threshold")
async def cortex_threshold_set(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).set_threshold(str(request.get("surface") or ""), float(request.get("value") or 0.7))

@router.post("/cortex/repair-enabled")
async def cortex_repair_enabled(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).set_repair_enabled(str(request.get("surface") or ""), bool(request.get("enabled")))

@router.post("/cortex/repair-class")
async def cortex_repair_class(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).set_repair_class(str(request.get("name") or ""), bool(request.get("enabled")))
