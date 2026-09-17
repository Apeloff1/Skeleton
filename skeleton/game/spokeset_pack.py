"""Named spoke sets."""

from __future__ import annotations

from typing import Any


class SpokesetPackError(ValueError):
    pass


SPOKE = tuple(f"sp_{i:02d}" for i in range(16))


def set_spoke(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in SPOKE:
        raise SpokesetPackError(name)
    nxt = dict(state)
    nxt["spokeset"] = name
    nxt["spokes"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
