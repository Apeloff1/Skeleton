"""Named tapers."""

from __future__ import annotations

from typing import Any


class TaperPackError(ValueError):
    pass


TAPER = tuple(f"tp_{i:02d}" for i in range(16))


def light(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TAPER:
        raise TaperPackError(name)
    nxt = dict(state)
    nxt["taper"] = name
    nxt["light"] = min(16, int(nxt.get("light", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
