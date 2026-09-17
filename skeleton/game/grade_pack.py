"""Named grades."""

from __future__ import annotations

from typing import Any


class GradePackError(ValueError):
    pass


GRADE = tuple(f"gd_{i:02d}" for i in range(24))


def set_grade(node: dict[str, Any], name: str, pct: int) -> dict[str, Any]:
    if name not in GRADE:
        raise GradePackError(name)
    nxt = dict(node)
    cur = dict(nxt.get("grade") or {})
    cur[name] = max(-8, min(8, int(pct)))
    nxt["grade"] = cur
    nxt["stored_prose"] = 0
    return nxt
