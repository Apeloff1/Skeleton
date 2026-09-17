"""Named mist lines."""

from __future__ import annotations

from typing import Any


class MistPackError(ValueError):
    pass


MIST = tuple(f"mi_{i:02d}" for i in range(16))


def spray(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MIST:
        raise MistPackError(name)
    nxt = dict(node)
    nxt["mist"] = name
    nxt["wet"] = min(16, int(nxt.get("wet", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
