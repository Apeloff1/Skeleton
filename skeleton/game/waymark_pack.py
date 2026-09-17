"""Named waymarks."""

from __future__ import annotations

from typing import Any


class WaymarkPackError(ValueError):
    pass


WAY = tuple(f"wm_{i:02d}" for i in range(16))


def set_way(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WAY:
        raise WaymarkPackError(name)
    nxt = dict(node)
    have = list(nxt.get("waymark") or [])
    have.append(name)
    nxt["waymark"] = have
    nxt["stored_prose"] = 0
    return nxt
