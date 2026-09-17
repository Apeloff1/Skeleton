"""Named hedge stakes."""

from __future__ import annotations

from typing import Any


class HedgestakePackError(ValueError):
    pass


STAKE = tuple(f"hs_{i:02d}" for i in range(16))


def drive(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAKE:
        raise HedgestakePackError(name)
    nxt = dict(state)
    have = list(nxt.get("hedgestake") or [])
    have.append(name)
    nxt["hedgestake"] = have
    nxt["stored_prose"] = 0
    return nxt
