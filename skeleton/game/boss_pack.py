"""Named bosses."""

from __future__ import annotations

from typing import Any


class BossPackError(ValueError):
    pass


BOSS = tuple(f"bs_{i:02d}" for i in range(8))


def set_boss(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOSS:
        raise BossPackError(name)
    nxt = dict(state)
    have = list(nxt.get("boss") or [])
    have.append(name)
    nxt["boss"] = have
    nxt["stored_prose"] = 0
    return nxt
