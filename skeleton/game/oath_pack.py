"""Named oaths."""

from __future__ import annotations

from typing import Any


class OathPackError(ValueError):
    pass


OATHS = tuple(f"oh_{i:02d}" for i in range(16))


def swear(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OATHS:
        raise OathPackError(name)
    nxt = dict(state)
    have = list(nxt.get("oath") or [])
    if name not in have:
        have.append(name)
    nxt["oath"] = have
    nxt["stored_prose"] = 0
    return nxt
