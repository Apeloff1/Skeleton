"""Named evidence bags. Pointer only."""

from __future__ import annotations

from typing import Any


class EvidencePackError(ValueError):
    pass


EV = tuple(f"ev_{i:02d}" for i in range(24))


def bag(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in EV:
        raise EvidencePackError(name)
    if not digest:
        raise EvidencePackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("evidence") or {})
    cur[name] = digest
    nxt["evidence"] = cur
    nxt["stored_prose"] = 0
    return nxt
