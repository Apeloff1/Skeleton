"""Named rakes."""

from __future__ import annotations

from typing import Any


class RakePackError(ValueError):
    pass


RAKE = tuple(f"rk_{i:02d}" for i in range(12))


def pull(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RAKE:
        raise RakePackError(name)
    nxt = dict(state)
    nxt["rake"] = name
    nxt["salt"] = int(nxt.get("salt", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
