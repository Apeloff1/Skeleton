"""Named escapements."""

from __future__ import annotations

from typing import Any


class EscapePackError(ValueError):
    pass


ESCAPE = tuple(f"es_{i:02d}" for i in range(12))


def tick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ESCAPE:
        raise EscapePackError(name)
    nxt = dict(state)
    nxt["escape"] = name
    nxt["tick"] = int(nxt.get("tick", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
