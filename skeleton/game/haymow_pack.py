"""Named hay mows."""

from __future__ import annotations

from typing import Any


class HaymowPackError(ValueError):
    pass


MOW = tuple(f"hm_{i:02d}" for i in range(8))


def set_mow(node: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in MOW:
        raise HaymowPackError(name)
    nxt = dict(node)
    nxt["haymow"] = name
    nxt["hay"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
