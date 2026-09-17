"""Named strands."""

from __future__ import annotations

from typing import Any


class StrandPackError(ValueError):
    pass


STRAND = tuple(f"st_{i:02d}" for i in range(16))


def set_strand(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STRAND:
        raise StrandPackError(name)
    nxt = dict(state)
    have = list(nxt.get("strand") or [])
    have.append(name)
    nxt["strand"] = have
    nxt["stored_prose"] = 0
    return nxt
