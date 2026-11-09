"""Pointer cards for SC-160. stored_prose stays 0."""

from __future__ import annotations

from typing import Any

from skeleton.supply_chain.vol178.law import CITATION, PACKET, PARENT


def supply_card(kind: str, hit: int, law: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
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
