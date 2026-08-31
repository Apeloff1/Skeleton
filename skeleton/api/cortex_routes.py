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


@router.get("/cortex/dodeca")
async def cortex_dodeca(state=Depends(_state)) -> Dict[str, Any]:
    deck = _deck(state)
    return {
        "faces": list(FACES),
        "position": deck.position,
        "face": FACES[deck.position],
        "card": face_card(deck.neo),
        "seed": 8847291,
    }


@router.post("/cortex/think")
async def cortex_think(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus", "")).strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    deck = _deck(state)
    ctx = {"era": request.get("era", "extraction_now")}
    trace = deck.neo.think(stimulus, ctx)
    return {"trace": trace.to_dict() if hasattr(trace, "to_dict") else trace}


@router.post("/cortex/speak")
async def cortex_speak(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus", "")).strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    return _deck(state).speak(stimulus)


@router.post("/cortex/refer")
async def cortex_refer(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus", "")).strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    return _deck(state).refer(stimulus, live=bool(request.get("live")))


@router.post("/cortex/improve")
async def cortex_improve(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus", "")).strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    rounds = int(request.get("rounds") or 6)
    return _deck(state).improve(stimulus, rounds=rounds)


@router.post("/cortex/ascend")
async def cortex_ascend(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus", "")).strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    rounds = int(request.get("rounds") or 6)
    return _deck(state).ascend(stimulus, rounds=rounds)


@router.post("/cortex/plan")
async def cortex_plan(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    vision = str(request.get("vision") or request.get("stimulus") or "").strip()
    if not vision:
        raise HTTPException(status_code=422, detail="vision is required")
    return _deck(state).plan(vision)


@router.post("/cortex/genos")
async def cortex_genos(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus") or "plan tensor ttk lattice soulslike")
    return _deck(state).genos(stimulus)


@router.post("/cortex/cut")
async def cortex_cut(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus") or request.get("vision") or "").strip()
    if not stimulus:
        raise HTTPException(status_code=422, detail="stimulus is required")
    rounds = int(request.get("rounds") or 3)
    return _deck(state).cut(stimulus, rounds=rounds, live=bool(request.get("live")))


@router.post("/cortex/dodeca/walk")
async def cortex_dodeca_walk(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    steps = int(request.get("steps") or 1)
    return _deck(state).walk(steps)


@router.post("/cortex/dodeca/pick")
async def cortex_dodeca_pick(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).pick(int(request.get("index") or 0))


@router.get("/cortex/galaxy")
async def cortex_galaxy_get() -> Dict[str, Any]:
    from skeleton.galaxy.system import live_galaxy
    return live_galaxy().snapshot()


@router.post("/cortex/galaxy")
async def cortex_galaxy_post(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus") or request.get("vision") or "").strip()
    return _deck(state).galaxy(stimulus, sleep=bool(request.get("sleep")))


@router.get("/cortex/social")
async def cortex_social_get(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).social("")


@router.post("/cortex/social")
async def cortex_social_post(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).social(str(request.get("stimulus") or request.get("url") or ""))


@router.get("/cortex/organismer")
async def cortex_organismer_get(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).organismer("")


@router.post("/cortex/organismer")
async def cortex_organismer_post(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    stimulus = str(request.get("stimulus") or request.get("vision") or "").strip()
    return _deck(state).organismer(stimulus, sleep=bool(request.get("sleep")))


@router.get("/cortex/product")
async def cortex_product_get(state=Depends(_state)) -> Dict[str, Any]:
    return _deck(state).product()
