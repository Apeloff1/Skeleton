"""Named lime putties."""

from __future__ import annotations

from typing import Any


class PuttyPackError(ValueError):
    pass


PUTTY = tuple(f"pt_{i:02d}" for i in range(12))


def age(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PUTTY:
        raise PuttyPackError(name)
    nxt = dict(state)
    nxt["putty"] = name
    nxt["age"] = int(nxt.get("age", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
