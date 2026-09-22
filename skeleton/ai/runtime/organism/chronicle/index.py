"""Master inverted index — token → book handles. Cap per token."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.laws import check
from skeleton.galaxy.atoms import token_set
from skeleton.organism.chronicle.books import index_path

PER_TOKEN = 24


def load(root: Optional[Path] = None) -> Dict[str, Any]:
    path = index_path(root)
    if not path.exists():
        return {"kind": "chronicle-index", "map": {}, "n": 0, "stored_prose": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"kind": "chronicle-index", "map": {}, "n": 0, "stored_prose": 0}


def save(card: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = check({
        "kind": "chronicle-index",
        "map": card.get("map") or {},
        "n": int(card.get("n") or 0),
        "stored_prose": 0,
    })
    path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
    return payload


def add(topic: str, *, book: str, ref: str, root: Optional[Path] = None) -> Dict[str, Any]:
    card = load(root)
    amap = card.setdefault("map", {})
    for tok in list(token_set(topic or ""))[:8]:
        hits: List[Dict[str, str]] = list(amap.get(tok) or [])
        hits.append({"book": book[:20], "ref": ref[:80]})
        amap[tok] = hits[-PER_TOKEN:]
    card["n"] = sum(len(v) for v in amap.values())
    return save(card, root=root)


def lookup(cue: str, *, root: Optional[Path] = None, k: int = 12) -> Dict[str, Any]:
    card = load(root)
    amap = card.get("map") or {}
    hits: List[Dict[str, str]] = []
    seen = set()
    for tok in token_set(cue or ""):
        for row in amap.get(tok) or []:
            key = row.get("book", "") + ":" + row.get("ref", "")
            if key in seen:
                continue
            seen.add(key)
            hits.append(row)
            if len(hits) >= k:
                break
        if len(hits) >= k:
            break
    return {"kind": "chronicle-lookup", "cue": (cue or "")[:80], "n": len(hits), "hits": hits, "stored_prose": 0}
