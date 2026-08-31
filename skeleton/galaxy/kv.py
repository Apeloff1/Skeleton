"""Handle archive — only when a transformer mouth is bound.

This is not a production KV cache. It stores topic → residual-hash
vectors (16 floats) for internalized atoms. Unbound mouths get
bound=0 and an empty map. Cap from live residual width.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.galaxy.banks import residual_block


def bound(neo) -> bool:
    return neo is not None and getattr(neo, "transformer", None) is not None


def archive(mesh, *, neo=None) -> Dict[str, Any]:
    if not bound(neo):
        return {"kind": "kv-archive", "bound": 0, "n": 0, "keys": [], "stored_prose": 0}
    try:
        from skeleton.organism.caps import live as live_caps
        cap = int(live_caps().residual)
    except Exception:
        cap = 16
    keys: List[str] = []
    store: Dict[str, List[float]] = {}
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if atom.superseded_by:
                continue
            if "internalized" not in (atom.tags or ()) and atom.kind != "principle":
                continue
            vec = residual_block(list(atom.tokens), n=cap)
            store[atom.id] = vec
            keys.append(atom.id)
            if len(store) >= cap * 4:
                break
    return {
        "kind": "kv-archive",
        "bound": 1,
        "n": len(store),
        "keys": keys[:32],
        "width": cap,
        "stored_prose": 0,
    }
