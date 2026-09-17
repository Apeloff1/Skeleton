"""Named tuyeres."""

from __future__ import annotations

from typing import Any


class TuyerePackError(ValueError):
    pass


TUYERE = tuple(f"ty_{i:02d}" for i in range(16))


def blow(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TUYERE:
        raise TuyerePackError(name)
    nxt = dict(node)
    nxt["tuyere"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
