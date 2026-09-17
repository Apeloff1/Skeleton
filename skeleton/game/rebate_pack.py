"""Named rebates."""

from __future__ import annotations

from typing import Any


class RebatePackError(ValueError):
    pass


REBATE = tuple(f"rb_{i:02d}" for i in range(12))


def plane(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in REBATE:
        raise RebatePackError(name)
    nxt = dict(node)
    nxt["rebate"] = name
    nxt["stored_prose"] = 0
    return nxt
