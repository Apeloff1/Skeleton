"""Named billets."""

from __future__ import annotations

from typing import Any


class BilletPackError(ValueError):
    pass


BILLET = tuple(f"bt_{i:02d}" for i in range(24))


def roll(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BILLET:
        raise BilletPackError(name)
    nxt = dict(state)
    have = list(nxt.get("billet") or [])
    have.append(name)
    nxt["billet"] = have
    nxt["stored_prose"] = 0
    return nxt
