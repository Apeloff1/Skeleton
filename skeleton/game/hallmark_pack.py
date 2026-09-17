"""Named hallmarks."""

from __future__ import annotations

from typing import Any


class HallmarkPackError(ValueError):
    pass


HALL = tuple(f"hm_{i:02d}" for i in range(12))


def punch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HALL:
        raise HallmarkPackError(name)
    nxt = dict(state)
    nxt["hallmark"] = name
    nxt["marked"] = 1
    nxt["stored_prose"] = 0
    return nxt
