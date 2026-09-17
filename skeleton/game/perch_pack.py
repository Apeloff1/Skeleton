"""Named perches."""

from __future__ import annotations

from typing import Any


class PerchPackError(ValueError):
    pass


PERCH = tuple(f"pe_{i:02d}" for i in range(8))


def measure(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in PERCH:
        raise PerchPackError(name)
    nxt = dict(state)
    nxt["perch"] = name
    nxt["rd"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
