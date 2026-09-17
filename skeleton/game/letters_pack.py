"""Named letters patent."""

from __future__ import annotations

from typing import Any


class LettersPackError(ValueError):
    pass


LETTERS = tuple(f"lp_{i:02d}" for i in range(8))


def issue(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LETTERS:
        raise LettersPackError(name)
    nxt = dict(state)
    nxt["letters"] = name
    nxt["issued"] = 1
    nxt["stored_prose"] = 0
    return nxt
