"""Named creels."""

from __future__ import annotations

from typing import Any


class CreelPackError(ValueError):
    pass


CREEL = tuple(f"cr_{i:02d}" for i in range(12))


def fill(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in CREEL:
        raise CreelPackError(name)
    nxt = dict(state)
    nxt["creel"] = name
    nxt["catch"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
