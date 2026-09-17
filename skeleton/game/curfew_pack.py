"""Named curfews."""

from __future__ import annotations

from typing import Any


class CurfewPackError(ValueError):
    pass


CURFEW = tuple(f"cf_{i:02d}" for i in range(16))


def on(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CURFEW:
        raise CurfewPackError(name)
    nxt = dict(state)
    nxt["curfew"] = name
    nxt["locked"] = 1
    nxt["stored_prose"] = 0
    return nxt
