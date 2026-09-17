"""Named survey chains."""

from __future__ import annotations

from typing import Any


class ChainPackError(ValueError):
    pass


CHAIN = tuple(f"cn_{i:02d}" for i in range(12))


def stretch(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in CHAIN:
        raise ChainPackError(name)
    nxt = dict(state)
    nxt["chain"] = name
    nxt["len"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
