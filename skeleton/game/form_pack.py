"""Named forms. Pointer only."""

from __future__ import annotations

from typing import Any


class FormPackError(ValueError):
    pass


FORM = tuple(f"fm_{i:02d}" for i in range(28))


def file(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in FORM:
        raise FormPackError(name)
    if not digest:
        raise FormPackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("form") or {})
    cur[name] = digest
    nxt["form"] = cur
    nxt["stored_prose"] = 0
    return nxt
