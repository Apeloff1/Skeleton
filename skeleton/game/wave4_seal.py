"""Seal helpers for wave-4 cards."""
from __future__ import annotations
from typing import Any
from skeleton.game.seal_card import seal

class Wave4SealError(ValueError):
    pass

def card(kind: str, seed: int, **fields: Any) -> dict[str, Any]:
    if not kind:
        raise Wave4SealError("kind")
    body = {"kind": kind, "seed": int(seed), "sota_ready": False, "stored_prose": 0}
    body.update(fields)
    return seal(body)

def extract_once(state: dict[str, Any]) -> dict[str, Any]:
    nxt = dict(state)
    if int(nxt.get("extracted", 0)) != 0:
        raise Wave4SealError("twice")
    if int(nxt.get("heat", 0)) < 8:
        raise Wave4SealError("cold")
    nxt["extracted"] = 1
    nxt["warp_count"] = 1
    nxt["stored_prose"] = 0
    return nxt
