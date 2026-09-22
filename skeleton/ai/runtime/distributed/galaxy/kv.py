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
        "store": store,
        "stored_prose": 0,
    }


def persist(mesh, *, neo=None, root=None) -> Dict[str, Any]:
    import json
    from skeleton.organism.paths import kv_path
    card = archive(mesh, neo=neo)
    if not card.get("bound"):
        return {**card, "persisted": 0}
    path = kv_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: card[k] for k in ("kind", "bound", "n", "keys", "width", "stored_prose") if k in card}
    payload["store"] = card.get("store") or {}
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    payload["persisted"] = 1
    payload["path"] = str(path)
    payload.pop("store", None)
    return payload


def load(*, root=None) -> Dict[str, Any]:
    import json
    from skeleton.organism.paths import kv_path
    path = kv_path(root)
    if not path.exists():
        return {"kind": "kv-archive", "bound": 0, "n": 0, "persisted": 0, "stored_prose": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"kind": "kv-archive", "bound": 0, "n": 0, "persisted": 0, "stored_prose": 0}
    data["persisted"] = 1
    data.pop("store", None)
    return data
