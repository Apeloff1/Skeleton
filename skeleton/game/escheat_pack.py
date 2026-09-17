"""Named escheats."""

from __future__ import annotations

from typing import Any


class EscheatPackError(ValueError):
    pass


ESCHEAT = tuple(f"es_{i:02d}" for i in range(8))


def revert(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ESCHEAT:
        raise EscheatPackError(name)
    nxt = dict(state)
    nxt["escheat"] = name
    nxt["reverted"] = 1
    nxt["stored_prose"] = 0
    return nxt
