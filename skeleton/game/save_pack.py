"""Named save slots. Pointer cards only."""

from __future__ import annotations

from typing import Any


class SavePackError(ValueError):
    pass


SLOTS = tuple(f"slot{i}" for i in range(12))


def blank() -> dict[str, Any]:
    return {name: None for name in SLOTS}


def write(bank: dict[str, Any], name: str, card: dict[str, Any]) -> dict[str, Any]:
    if name not in SLOTS:
        raise SavePackError(name)
    nxt = dict(bank)
    nxt[name] = {
        "digest": card.get("digest"),
        "kind": card.get("kind"),
        "extract_count": card.get("extract_count", 0),
        "stored_prose": 0,
    }
    return nxt


def read(bank: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SLOTS:
        raise SavePackError(name)
    card = bank.get(name)
    if not card:
        raise SavePackError("empty")
    return dict(card)
