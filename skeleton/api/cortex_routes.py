"""Cortex command deck — inspect AND speak.

Now includes repair orchestrator and adaptive policy endpoints.
"""
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

# Repair orchestrator endpoints
@router.get("/cortex/repair-sessions")
async def cortex_repair_sessions(surface: str = "", limit: int = 8, state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repair_sessions(surface=surface, limit=limit)

@router.get("/cortex/repair-effectiveness")
async def cortex_repair_effectiveness(surface: str = "", state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repair_effectiveness(surface=surface)

@router.get("/cortex/repair-telemetry")
async def cortex_repair_telemetry(surface: str = "", limit: int = 16, state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repair_telemetry(surface=surface, limit=limit)

@router.get("/cortex/repair-errors")
async def cortex_repair_errors(surface: str = "", state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repair_errors(surface=surface)

@router.get("/cortex/learned-policy")
async def cortex_learned_policy(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).learned_policy()

@router.get("/cortex/repair-orchestrator")
async def cortex_repair_orchestrator(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repair_orchestrator()

# Adaptive policy endpoints
@router.get("/cortex/adaptive-policy")
async def cortex_adaptive_policy(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).adaptive_policy()

@router.get("/cortex/adapt")
async def cortex_adapt(surface: str = "", dry_run: bool = False, state=Depends(_state)) -> Dict[str, Any]:
    if surface:
        return _deck(state).adapt_surface(surface, dry_run=dry_run)
    return _deck(state).adapt_all(dry_run=dry_run)

@router.post("/cortex/adaptive-config")
async def cortex_adaptive_config(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).set_adaptive_config(**request)

@router.post("/cortex/adaptive-surface-config")
async def cortex_adaptive_surface_config(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    surface = str(request.pop("surface", ""))
    return _deck(state).set_surface_adaptive(surface, **request)
