"""Named key bows."""

from __future__ import annotations

from typing import Any


class LockbowPackError(ValueError):
    pass


BOW = tuple(f"lw_{i:02d}" for i in range(12))


def set_bow(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOW:
        raise LockbowPackError(name)
    nxt = dict(state)
    nxt["lockbow"] = name
    nxt["stored_prose"] = 0
    return nxt
