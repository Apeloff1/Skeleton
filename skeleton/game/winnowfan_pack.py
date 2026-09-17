"""Named winnow fans."""

from __future__ import annotations

from typing import Any


class WinnowfanPackError(ValueError):
    pass


FAN = tuple(f"wf_{i:02d}" for i in range(8))


def toss(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FAN:
        raise WinnowfanPackError(name)
    nxt = dict(state)
    nxt["winnowfan"] = name
    nxt["air"] = int(nxt.get("air", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
