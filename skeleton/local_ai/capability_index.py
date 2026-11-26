"""
Registry of adapter capability cards. Every Wave 3 layer exports capabilities with owner contract failure_modes obs security.
"""
from __future__ import annotations

import re

from .seam_runtime import admit, stamp

CARDS: list[dict] = []
_CAP = 64
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def export(name: str, owner: str) -> None:
    if not isinstance(name, str) or not isinstance(owner, str):
        raise ValueError("capability card is invalid")
    if not _NAME.fullmatch(name) or not _NAME.fullmatch(owner):
        raise ValueError("capability card is invalid")
    card = {"name": name, "owner": owner}
    if card in CARDS:
        return
    if len(CARDS) >= _CAP:
        raise ValueError("capability registry is full")
    CARDS.append(card)


def process(data: dict) -> dict:
    refused = admit("capability_index", data)
    if refused:
        return refused
    if "name" not in data and "owner" not in data:
        return stamp("capability_index", data, {"cards": len(CARDS)})
    try:
        export(data.get("name"), data.get("owner"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "card": "capability_index"}
    return stamp("capability_index", data, {"cards": len(CARDS)})
