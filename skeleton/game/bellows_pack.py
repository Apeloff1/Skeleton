"""Named bellows."""

from __future__ import annotations

from typing import Any


class BellowsPackError(ValueError):
    pass


BELLOWS = tuple(f"bw_{i:02d}" for i in range(16))


def pump(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BELLOWS:
        raise BellowsPackError(name)
    nxt = dict(node)
    nxt["bellows"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
