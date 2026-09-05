"""Halt mix — ponder score + overthink delta in one card."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.overthink import run as overthink
from skeleton.kernel.ops.ponder import ponder

Row = List[float]


def haltmix(x: Row, *, r_max: int = 4) -> dict:
    card = overthink(x, r_max=r_max)
    score = ponder(card.get("h") or x)
    bump(1)
    return {
        "kind": "halt-mix",
        "used": card.get("used"),
        "halted": card.get("halted"),
        "ponder": score,
        "h": card.get("h"),
        "stored_prose": 0,
    }
