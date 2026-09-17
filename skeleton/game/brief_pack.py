"""Named briefs. Pointer only."""

from __future__ import annotations

from typing import Any


class BriefPackError(ValueError):
    pass


BRIEF = tuple(f"bf_{i:02d}" for i in range(24))


def set_brief(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in BRIEF:
        raise BriefPackError(name)
    if not digest:
        raise BriefPackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("brief") or {})
    cur[name] = digest
    nxt["brief"] = cur
    nxt["stored_prose"] = 0
    return nxt
