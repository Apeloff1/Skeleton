"""Named ledger notes. Pointer only."""

from __future__ import annotations

from typing import Any


class NotePackError(ValueError):
    pass


NOTES = tuple(f"nt_{i:02d}" for i in range(24))


def write(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in NOTES:
        raise NotePackError(name)
    if not digest:
        raise NotePackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("note") or {})
    cur[name] = digest
    nxt["note"] = cur
    nxt["stored_prose"] = 0
    return nxt
