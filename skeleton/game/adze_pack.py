"""Named adzes."""

from __future__ import annotations

from typing import Any


class AdzePackError(ValueError):
    pass


ADZE = tuple(f"az_{i:02d}" for i in range(12))


def hew(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ADZE:
        raise AdzePackError(name)
    nxt = dict(state)
    nxt["adze"] = name
    nxt["hewn"] = int(nxt.get("hewn", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
