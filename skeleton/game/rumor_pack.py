"""Named rumors. Pointer only."""

from __future__ import annotations

from typing import Any


class RumorPackError(ValueError):
    pass


RUMOR = tuple(f"ru_{i:02d}" for i in range(24))


def hear(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RUMOR:
        raise RumorPackError(name)
    nxt = dict(state)
    have = list(nxt.get("rumor") or [])
    if name not in have:
        have.append(name)
    nxt["rumor"] = have
    nxt["stored_prose"] = 0
    return nxt
