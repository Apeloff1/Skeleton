"""Cortex command deck — inspect AND speak.

Read surface stays. Mutation paths (speak / refer / improve / ascend /
plan / genos / dodeca) are the organism the CLI already had; HTTP now
carries the same mouth. Genesis handle if wired; live_cortex otherwise.
Laws gate every write. Pointers only.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from skeleton.api.server import get_state
from skeleton.cortex.deck import CommandDeck
from skeleton.cortex.dodeca import FACES, face_card
from skeleton.cortex.laws import LAWS
from skeleton.cortex.refs import index as refs_index

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

@router.get("/cortex/status")
async def cortex_status(state=Depends(_state)) -> Dict[str, Any]:
    deck = _deck(state)
    return {"cortex": deck.status()}

@router.get("/cortex/deck")
async def cortex_deck(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).snapshot()

@router.get("/cortex/laws")
async def cortex_laws() -> Dict[str, Any]:
    return {"laws": list(LAWS), "stored_prose": 0}

@router.get("/cortex/refs")
async def cortex_refs() -> Dict[str, Any]:
    return {"refs": refs_index(), "stored_prose": 0}

@router.get("/cortex/failures")
async def cortex_failures(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).failures()

@router.get("/cortex/repairs")
async def cortex_repairs(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).repairs()

@router.get("/cortex/activity")
async def cortex_activity(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).activity()

@router.get("/cortex/recurring")
async def cortex_recurring(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).recurring()
