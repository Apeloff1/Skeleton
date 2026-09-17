"""Named malt kilns."""

from __future__ import annotations

from typing import Any


class KilnmaltPackError(ValueError):
    pass


KILN = tuple(f"km_{i:02d}" for i in range(8))


def dry(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in KILN:
        raise KilnmaltPackError(name)
    nxt = dict(state)
    nxt["kilnmalt"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
