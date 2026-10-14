"""Lazy registry. Count comes from the index."""

from __future__ import annotations

from typing import Any

from skeleton.audio.eras.caps import names
from skeleton.audio.eras.law import CAPABILITY_COUNT, LAYER, PACKET, VERSION


def index() -> dict[str, str]:
    return {cid: module for cid, _era, module in names()}


def capabilities() -> dict[str, Any]:
    rows = names()
    if len(rows) != CAPABILITY_COUNT:
        raise RuntimeError("capability-count")
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "count": len(rows),
        "eras": sorted({era for _cid, era, _module in rows}),
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0, "sample_bank": 0},
        "stored_prose": 0,
    }
