"""Named call slips."""

from __future__ import annotations

from typing import Any


class SlipPackError(ValueError):
    pass


SLIP = tuple(f"sp_{i:02d}" for i in range(28))


def write(state: dict[str, Any], name: str, folio: str) -> dict[str, Any]:
    if name not in SLIP:
        raise SlipPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("slip") or {})
    cur[name] = folio
    nxt["slip"] = cur
    nxt["stored_prose"] = 0
    return nxt
