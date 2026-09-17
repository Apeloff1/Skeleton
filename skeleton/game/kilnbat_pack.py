"""Named kiln bats."""

from __future__ import annotations

from typing import Any


class KilnbatPackError(ValueError):
    pass


BAT = tuple(f"kb_{i:02d}" for i in range(12))


def set_bat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BAT:
        raise KilnbatPackError(name)
    nxt = dict(state)
    nxt["kilnbat"] = name
    nxt["stored_prose"] = 0
    return nxt
