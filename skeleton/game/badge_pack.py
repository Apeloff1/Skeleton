"""Named badges."""

from __future__ import annotations

from typing import Any


class BadgePackError(ValueError):
    pass


BADGE = tuple(f"bd_{i:02d}" for i in range(24))


def pin(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BADGE:
        raise BadgePackError(name)
    nxt = dict(state)
    have = list(nxt.get("badge") or [])
    if name not in have:
        have.append(name)
    nxt["badge"] = have
    nxt["stored_prose"] = 0
    return nxt
