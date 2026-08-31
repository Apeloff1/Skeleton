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


def clip_fat(mesh) -> Dict[str, Any]:
    from skeleton.galaxy.atoms import house_dialect
    clipped = 0
    for lib in (mesh.brains or {}).values():
        shelf = getattr(lib, "shelf", {}) or {}
        items = shelf.values() if isinstance(shelf, dict) else shelf
        for atom in items:
            dialect = str(getattr(atom, "dialect", "") or "")
            topic = str(getattr(atom, "topic", "") or "")
            if len(f"{dialect} {topic}".split()) > LIMIT:
                atom.dialect = house_dialect(dialect or topic)
                if len(topic.split()) > LIMIT:
                    atom.topic = " ".join(topic.split()[:8])
                clipped += 1
    return {"kind": "clip", "clipped": clipped, "stored_prose": scan_prose(mesh)}


def persist_clip(org) -> Dict[str, Any]:
    if not getattr(org, "persist_on", False):
        return {"persisted": 0}
    from skeleton.galaxy.shelf import save
    card = save(org.galaxy, root=getattr(org, "root", None))
    card["persisted"] = 1
    return card


def laws_card(mesh) -> Dict[str, Any]:
    prose = scan_prose(mesh)
    return {
        "kind": "laws",
        "stored_prose": prose,
        "ok": int(prose == 0),
        "limit_tokens": LIMIT,
        "names": ("cite-do-not-copy", "stored_prose=0", "clipped-G", "headroom-below-wall"),
    }
