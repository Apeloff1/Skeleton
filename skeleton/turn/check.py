"""GB-50 check. A stamp does not pass. A move does."""

from __future__ import annotations


def _bit(card: dict, key: str) -> int:
    value = card.get(key)
    if value == 0:
        return 0
    return 1


def check(card: dict) -> dict:
    stamp = _bit(card, "stamp")
    rebuild = _bit(card, "rebuild")
    return {
        "kind": "check",
        "ok": 1 if stamp == 0 and rebuild == 0 else 0,
        "stamp": stamp,
        "rebuild": rebuild,
        "stored_prose": 0,
    }
