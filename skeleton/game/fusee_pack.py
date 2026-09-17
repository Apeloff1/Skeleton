"""Named fusees."""

from __future__ import annotations

from typing import Any


class FuseePackError(ValueError):
    pass


FUSEE = tuple(f"fe_{i:02d}" for i in range(12))


def wind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FUSEE:
        raise FuseePackError(name)
    nxt = dict(state)
    nxt["fusee"] = name
    nxt["wind"] = int(nxt.get("wind", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
