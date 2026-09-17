"""Named punch clocks."""

from __future__ import annotations

from typing import Any


class PunchPackError(ValueError):
    pass


PUNCH = tuple(f"pc_{i:02d}" for i in range(16))


def clock_in(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PUNCH:
        raise PunchPackError(name)
    nxt = dict(state)
    nxt["punch"] = name
    nxt["tokens"] = int(nxt.get("tokens", 8)) + 1
    nxt["stored_prose"] = 0
    return nxt
