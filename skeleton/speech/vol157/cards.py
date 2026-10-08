"""Pointer cards for SPEECH-80. stored_prose stays 0."""

from __future__ import annotations

from typing import Any

from skeleton.speech.vol157.law import CITATION, PACKET, PARENT


def speech_card(kind: str, hit: int, law: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
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
        if "stored_prose" in extra and extra["stored_prose"] != 0:
            raise ValueError("stored_prose")
        card.update(extra)
        card["stored_prose"] = 0
    return card
