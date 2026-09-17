"""Named rubrics."""

from __future__ import annotations

from typing import Any


class RubricPackError(ValueError):
    pass


RUBRIC = tuple(f"rb_{i:02d}" for i in range(12))


def mark(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RUBRIC:
        raise RubricPackError(name)
    nxt = dict(state)
    nxt["rubric"] = name
    nxt["red"] = 1
    nxt["stored_prose"] = 0
    return nxt
