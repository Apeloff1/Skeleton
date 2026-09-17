"""Named type sorts. Pointer only."""

from __future__ import annotations

from typing import Any


class TypePackError(ValueError):
    pass


TYPE = tuple(f"ty_{i:02d}" for i in range(16))


def set_sort(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in TYPE:
        raise TypePackError(name)
    if not digest:
        raise TypePackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("type") or {})
    cur[name] = digest
    nxt["type"] = cur
    nxt["stored_prose"] = 0
    return nxt
