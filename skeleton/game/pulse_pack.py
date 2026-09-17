"""Named heat pulses."""

from __future__ import annotations

from typing import Any


class PulsePackError(ValueError):
    pass


PULSE = tuple(f"pu_{i:02d}" for i in range(24))


def beat(node: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in PULSE:
        raise PulsePackError(name)
    nxt = dict(node)
    nxt["pulse"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((t + PULSE.index(name)) % 3) - 1))
    nxt["stored_prose"] = 0
    return nxt
