"""Named drill rows."""

from __future__ import annotations

from typing import Any


class DrillrowPackError(ValueError):
    pass


ROW = tuple(f"dr_{i:02d}" for i in range(16))


def sow(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ROW:
        raise DrillrowPackError(name)
    nxt = dict(state)
    have = list(nxt.get("drillrow") or [])
    have.append(name)
    nxt["drillrow"] = have
    nxt["stored_prose"] = 0
    return nxt
