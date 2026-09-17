"""Named mortises."""

from __future__ import annotations

from typing import Any


class MortisePackError(ValueError):
    pass


MORTISE = tuple(f"mo_{i:02d}" for i in range(16))


def cut(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MORTISE:
        raise MortisePackError(name)
    nxt = dict(node)
    nxt["mortise"] = name
    nxt["stored_prose"] = 0
    return nxt
