"""Named pecks."""

from __future__ import annotations

from typing import Any


class PeckPackError(ValueError):
    pass


PECK = tuple(f"pk_{i:02d}" for i in range(12))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in PECK:
        raise PeckPackError(name)
    nxt = dict(state)
    nxt["peck"] = name
    nxt["pk"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
