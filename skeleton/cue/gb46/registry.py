"""Lazy capability registry. Count comes from the index, not a mass import."""

from __future__ import annotations

from typing import Any

from skeleton.cue.gb46.caps import names
from skeleton.cue.gb46.law import CAPABILITY_COUNT, LAYER, PACKET, VERSION


def index() -> dict[str, str]:
    return {cid: module for cid, _family, module in names()}


def capabilities() -> dict[str, Any]:
    rows = names()
    if len(rows) != CAPABILITY_COUNT:
        raise RuntimeError("capability-count")
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "count": len(rows),
        "families": sorted({family for _cid, family, _module in rows}),
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0},
        "stored_prose": 0,
    }
