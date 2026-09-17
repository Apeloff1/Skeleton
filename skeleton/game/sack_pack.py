"""Named sacks."""

from __future__ import annotations

from typing import Any


class SackPackError(ValueError):
    pass


SACK = tuple(f"sk_{i:02d}" for i in range(16))


def fill(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SACK:
        raise SackPackError(name)
    nxt = dict(state)
    have = list(nxt.get("sack") or [])
    have.append(name)
    nxt["sack"] = have
    nxt["stored_prose"] = 0
    return nxt
