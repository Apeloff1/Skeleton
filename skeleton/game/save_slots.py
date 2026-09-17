"""Sealed save slots. Four slots. Digest only."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal


SLOTS = ("slot0", "slot1", "slot2", "slot3")


class SaveError(ValueError):
    pass


def blank_bank() -> dict[str, Any]:
    bank: dict[str, Any] = {name: None for name in SLOTS}
    bank["kind"] = "save_bank"
    bank["stored_prose"] = 0
    return bank


def write(bank: dict[str, Any], slot: str, card: dict[str, Any]) -> dict[str, Any]:
    if slot not in SLOTS:
        raise SaveError("slot")
    if not isinstance(card, dict):
        raise SaveError("card")
    nxt = dict(bank)
    body = seal(dict(card))
    nxt[slot] = {"digest": body["digest"], "kind": body.get("kind"), "sota_ready": False}
    nxt["stored_prose"] = 0
    return nxt


def read(bank: dict[str, Any], slot: str) -> dict[str, Any]:
    if slot not in SLOTS:
        raise SaveError("slot")
    row = bank.get(slot)
    if not row:
        raise SaveError("empty")
    return dict(row)
