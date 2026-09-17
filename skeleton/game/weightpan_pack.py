"""Named weight pans."""

from __future__ import annotations

from typing import Any


class WeightpanPackError(ValueError):
    pass


PAN = tuple(f"wp_{i:02d}" for i in range(8))


def set_pan(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in PAN:
        raise WeightpanPackError(name)
    nxt = dict(state)
    nxt["weightpan"] = name
    nxt["load"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
