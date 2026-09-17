"""Named sleepers."""

from __future__ import annotations

from typing import Any


class SleeperPackError(ValueError):
    pass


SLEEPER = tuple(f"sl_{i:02d}" for i in range(28))


def set_sleeper(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SLEEPER:
        raise SleeperPackError(name)
    nxt = dict(node)
    have = list(nxt.get("sleeper") or [])
    if name not in have:
        have.append(name)
    nxt["sleeper"] = have
    nxt["stored_prose"] = 0
    return nxt
