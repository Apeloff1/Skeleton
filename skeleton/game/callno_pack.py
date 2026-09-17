"""Named call numbers."""

from __future__ import annotations

from typing import Any


class CallnoPackError(ValueError):
    pass


CALL = tuple(f"cn_{i:02d}" for i in range(28))


def assign(state: dict[str, Any], name: str, folio: str) -> dict[str, Any]:
    if name not in CALL:
        raise CallnoPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("callno") or {})
    cur[folio] = name
    nxt["callno"] = cur
    nxt["stored_prose"] = 0
    return nxt
