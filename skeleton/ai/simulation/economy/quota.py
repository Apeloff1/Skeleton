"""GB-51 quota. Cap 8. Spaced items drop. No coin."""

from __future__ import annotations

CAP = 8


def _token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    if not value or " " in value or len(value) > 32:
        return ""
    return value


def admit(items: list) -> dict:
    kept: list[str] = []
    dropped = 0
    for item in items:
        token = _token(item)
        if not token or len(kept) >= CAP:
            dropped += 1
            continue
        kept.append(token)
    return {
        "kind": "quota",
        "n": len(kept),
        "cap": CAP,
        "kept": kept,
        "dropped": dropped,
        "coin": 0,
        "stored_prose": 0,
    }
