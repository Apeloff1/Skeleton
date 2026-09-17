"""Wave-4 stealth stances."""

from __future__ import annotations

from typing import Any


class StanceWaveError(ValueError):
    pass


STN = {f"stn_{i:02d}": (i % 4) - 2 for i in range(16)}


def apply(state: dict[str, Any], name: str, seen: bool) -> dict[str, Any]:
    if name not in STN:
        raise StanceWaveError(name)
    nxt = dict(state)
    nxt["stance"] = name
    nxt["alert"] = max(0, int(nxt.get("alert", 0)) + (STN[name] if seen else -1))
    nxt["stored_prose"] = 0
    return nxt
