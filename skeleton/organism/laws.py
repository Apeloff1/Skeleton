"""Live law scan. stored_prose is counted, not stamped."""
from __future__ import annotations

from typing import Any, Dict

LIMIT = 24


def scan_prose(mesh) -> int:
    n = 0
    for lib in (mesh.brains or {}).values():
        shelf = getattr(lib, "shelf", {}) or {}
        items = shelf.values() if isinstance(shelf, dict) else shelf
        for atom in items:
            text = f"{getattr(atom, 'dialect', '')} {getattr(atom, 'topic', '')}"
            if len(text.split()) > LIMIT:
                n += 1
    return n


def laws_card(mesh) -> Dict[str, Any]:
    prose = scan_prose(mesh)
    return {
        "kind": "laws",
        "stored_prose": prose,
        "ok": int(prose == 0),
        "limit_tokens": LIMIT,
        "names": ("cite-do-not-copy", "stored_prose=0", "clipped-G", "headroom-below-wall"),
    }
