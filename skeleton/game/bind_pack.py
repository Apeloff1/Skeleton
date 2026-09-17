"""Named bindings."""

from __future__ import annotations

from typing import Any


class BindPackError(ValueError):
    pass


BIND = tuple(f"bn_{i:02d}" for i in range(20))


def sew(state: dict[str, Any], name: str, folio: str) -> dict[str, Any]:
    if name not in BIND:
        raise BindPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("bind") or {})
    cur[name] = folio
    nxt["bind"] = cur
    nxt["stored_prose"] = 0
    return nxt
