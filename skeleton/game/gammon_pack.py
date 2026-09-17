"""Named gammons."""

from __future__ import annotations

from typing import Any


class GammonPackError(ValueError):
    pass


GAMMON = tuple(f"gm_{i:02d}" for i in range(12))


def hang(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GAMMON:
        raise GammonPackError(name)
    nxt = dict(state)
    have = list(nxt.get("gammon") or [])
    have.append(name)
    nxt["gammon"] = have
    nxt["stored_prose"] = 0
    return nxt
