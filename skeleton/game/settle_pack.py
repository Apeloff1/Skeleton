"""Named settles."""

from __future__ import annotations

from typing import Any


class SettlePackError(ValueError):
    pass


SETTLE = tuple(f"se_{i:02d}" for i in range(12))


def set_settle(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SETTLE:
        raise SettlePackError(name)
    nxt = dict(node)
    nxt["settle"] = name
    nxt["stored_prose"] = 0
    return nxt
