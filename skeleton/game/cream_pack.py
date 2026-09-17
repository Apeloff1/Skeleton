"""Named cream lots."""

from __future__ import annotations

from typing import Any


class CreamPackError(ValueError):
    pass


CREAM = tuple(f"cr_{i:02d}" for i in range(12))


def skim(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CREAM:
        raise CreamPackError(name)
    nxt = dict(state)
    nxt["cream"] = name
    nxt["fat"] = int(nxt.get("fat", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
