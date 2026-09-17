"""Named hides."""

from __future__ import annotations

from typing import Any


class HidePackError(ValueError):
    pass


HIDE = tuple(f"hd_{i:02d}" for i in range(20))


def take(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HIDE:
        raise HidePackError(name)
    nxt = dict(state)
    have = list(nxt.get("hide") or [])
    have.append(name)
    nxt["hide"] = have
    nxt["stored_prose"] = 0
    return nxt
