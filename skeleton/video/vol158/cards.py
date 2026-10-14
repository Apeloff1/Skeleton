"""Pointer cards for VID-320. stored_prose stays 0."""

from __future__ import annotations

from typing import Any

from skeleton.video.vol158.law import CITATION, PACKET, PARENT


def video_card(kind: str, hit: int, law: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    card: dict[str, Any] = {
        "kind": kind,
        "hit": int(hit),
        "law": law,
        "citation": CITATION,
        "stored_prose": 0,
        "packet": PACKET,
        "parent": PARENT,
    }
    if extra:
        if extra.get("stored_prose", 0) != 0:
            raise ValueError("stored_prose")
        card.update(extra)
        card["stored_prose"] = 0
    return card
