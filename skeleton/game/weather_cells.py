"""Named weather cells."""

from __future__ import annotations

from typing import Any


class WeatherCellError(ValueError):
    pass


WX = {f"wx_{i:02d}": ((i % 5) - 2, i % 3) for i in range(40)}


def tick(name: str, node: dict[str, Any], t: int) -> dict[str, Any]:
    if name not in WX:
        raise WeatherCellError(name)
    dh, df = WX[name]
    nxt = dict(node)
    nxt["wx"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + dh + (t % 3) - 1))
    nxt["fog"] = max(0, min(8, int(nxt.get("fog", 0)) + df - 1))
    nxt["stored_prose"] = 0
    return nxt
