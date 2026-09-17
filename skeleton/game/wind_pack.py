"""Named wind loads."""

from __future__ import annotations

from typing import Any


class WindPackError(ValueError):
    pass


WIND = tuple(f"wn_{i:02d}" for i in range(28))


def set_wind(node: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in WIND:
        raise WindPackError(name)
    nxt = dict(node)
    nxt["wind"] = name
    nxt["force"] = max(0, min(16, int(n)))
    nxt["stored_prose"] = 0
    return nxt
