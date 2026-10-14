"""Capability registry for the VOL-156 batch."""

from __future__ import annotations

from typing import Any

from skeleton.audio.vol156.caps import ORGANS
from skeleton.audio.vol156.law import CAPABILITY_COUNT, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    items = []
    for cid, name, organ_cls in ORGANS:
        card = organ_cls().capabilities()
        card["id"] = cid
        card["name"] = name
        items.append(card)
    if len(items) != CAPABILITY_COUNT:
        raise RuntimeError("capability-count")
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "count": len(items),
        "items": items,
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed", "coin": 0},
        "stored_prose": 0,
    }


def index() -> dict[str, str]:
    return {cid: name for cid, name, _ in ORGANS}
