"""Named clinches."""

from __future__ import annotations

from typing import Any


class ClinchPackError(ValueError):
    pass


CLINCH = tuple(f"cl_{i:02d}" for i in range(12))


def bend(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLINCH:
        raise ClinchPackError(name)
    nxt = dict(state)
    nxt["clinch"] = name
    nxt["set"] = int(nxt.get("set", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
