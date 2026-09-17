"""Named lock patterns."""

from __future__ import annotations

from typing import Any


class LockPatternError(ValueError):
    pass


LOCKS = {f"lock_{i:02d}": 1 + (i % 3) for i in range(36)}


def make(name: str) -> dict[str, Any]:
    if name not in LOCKS:
        raise LockPatternError(name)
    return {"lock": name, "keys": LOCKS[name], "open": False, "stored_prose": 0}


def open_lock(name: str, state: dict[str, Any]) -> dict[str, Any]:
    if name not in LOCKS:
        raise LockPatternError(name)
    nxt = dict(state)
    need = LOCKS[name]
    if int(nxt.get("key", 0)) < need:
        raise LockPatternError("key")
    nxt["key"] = int(nxt.get("key", 0)) - need
    nxt["opened"] = name
    nxt["stored_prose"] = 0
    return nxt
