"""Named pendulums."""

from __future__ import annotations

from typing import Any


class PendulumPackError(ValueError):
    pass


PEND = tuple(f"pd_{i:02d}" for i in range(12))


def set_len(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in PEND:
        raise PendulumPackError(name)
    nxt = dict(state)
    nxt["pendulum"] = name
    nxt["len"] = max(1, min(16, int(n)))
    nxt["stored_prose"] = 0
    return nxt
