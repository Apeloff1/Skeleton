"""Named folios. Pointer only."""

from __future__ import annotations

from typing import Any


class FolioPackError(ValueError):
    pass


FOLIO = tuple(f"fo_{i:02d}" for i in range(28))


def open_folio(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in FOLIO:
        raise FolioPackError(name)
    if not digest:
        raise FolioPackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("folio") or {})
    cur[name] = digest
    nxt["folio"] = cur
    nxt["stored_prose"] = 0
    return nxt
