"""Named statutes."""

from __future__ import annotations

from typing import Any


class StatutePackError(ValueError):
    pass


STATUTE = tuple(f"st_{i:02d}" for i in range(12))


def enact(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STATUTE:
        raise StatutePackError(name)
    nxt = dict(state)
    nxt["statute"] = name
    nxt["law"] = 1
    nxt["stored_prose"] = 0
    return nxt
