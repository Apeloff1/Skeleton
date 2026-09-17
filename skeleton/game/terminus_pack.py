"""Named termini."""

from __future__ import annotations

from typing import Any


class TerminusPackError(ValueError):
    pass


TERM = tuple(f"tm_{i:02d}" for i in range(8))


def bound(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TERM:
        raise TerminusPackError(name)
    nxt = dict(state)
    nxt["terminus"] = name
    nxt["bound"] = 1
    nxt["stored_prose"] = 0
    return nxt
