"""Named wood ricks."""

from __future__ import annotations

from typing import Any


class RickPackError(ValueError):
    pass


RICK = tuple(f"rk_{i:02d}" for i in range(16))


def stack(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RICK:
        raise RickPackError(name)
    nxt = dict(state)
    have = list(nxt.get("rick") or [])
    have.append(name)
    nxt["rick"] = have
    nxt["stored_prose"] = 0
    return nxt
