"""Named peat cuts."""

from __future__ import annotations

from typing import Any


class PeatcutPackError(ValueError):
    pass


CUT = tuple(f"pc_{i:02d}" for i in range(12))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CUT:
        raise PeatcutPackError(name)
    nxt = dict(state)
    nxt["peatcut"] = name
    nxt["sod"] = int(nxt.get("sod", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
