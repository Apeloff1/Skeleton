"""Named quires."""

from __future__ import annotations

from typing import Any


class QuirePackError(ValueError):
    pass


QUIRE = tuple(f"qr_{i:02d}" for i in range(12))


def fold(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in QUIRE:
        raise QuirePackError(name)
    nxt = dict(state)
    nxt["quire"] = name
    nxt["leaves"] = max(1, int(n))
    nxt["stored_prose"] = 0
    return nxt
