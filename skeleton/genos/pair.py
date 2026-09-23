"""GB-49 pair gate. Two tokens. No sentence in the pair."""

from __future__ import annotations


def _token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    if not value or " " in value or len(value) > 32:
        return ""
    return value


def admit_pair(a: object, b: object) -> dict:
    left = _token(a)
    right = _token(b)
    ok = 1 if left and right else 0
    return {
        "kind": "genos-pair",
        "ok": ok,
        "n": 2 if ok else 0,
        "stored_prose": 0,
    }
