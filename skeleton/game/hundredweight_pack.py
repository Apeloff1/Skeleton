"""Named hundredweights."""

from __future__ import annotations

from typing import Any


class HundredweightPackError(ValueError):
    pass


CWT = tuple(f"cw_{i:02d}" for i in range(8))


def weigh(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in CWT:
        raise HundredweightPackError(name)
    nxt = dict(state)
    nxt["hundredweight"] = name
    nxt["cwt"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
