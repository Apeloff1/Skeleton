"""Rolodex — houses, teachers, field topics, self handle.

Cards are handles. No emails, tokens, or article bodies.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from skeleton.cortex.laws import check
from skeleton.organism.chronicle.books import rolodex_path


def _empty() -> Dict[str, Any]:
    return {
        "kind": "rolodex",
        "self": {"handle": "house", "role": "operator"},
        "houses": {},
        "teachers": {},
        "field": {},
        "topics": {},
        "n": 0,
        "stored_prose": 0,
    }


def load(root: Optional[Path] = None) -> Dict[str, Any]:
    path = rolodex_path(root)
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty()
    data.setdefault("stored_prose", 0)
    return data


def save(card: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = rolodex_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = check({
        "kind": "rolodex",
        "self": card.get("self") or {"handle": "house", "role": "operator"},
        "houses": card.get("houses") or {},
        "teachers": card.get("teachers") or {},
        "field": card.get("field") or {},
        "topics": card.get("topics") or {},
        "n": int(card.get("n") or 0),
        "stored_prose": 0,
    })
    path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
    return payload


def see(kind: str, name: str, *, meta: Optional[Dict[str, Any]] = None,
        root: Optional[Path] = None) -> Dict[str, Any]:
    card = load(root)
    bucket = {
        "house": "houses", "teacher": "teachers", "field": "field", "topic": "topics",
    }.get(kind, "topics")
    slot = card.setdefault(bucket, {})
    rec = slot.get(name) or {"name": name[:80], "seen": 0, "kind": kind}
    rec["seen"] = int(rec.get("seen") or 0) + 1
    if meta:
        url = str(meta.get("url") or "")[:240]
        if url:
            rec["url"] = url
        house = str(meta.get("house") or "")[:40]
        if house:
            rec["house"] = house
    slot[name[:80]] = rec
    card["n"] = sum(len(card.get(k) or {}) for k in ("houses", "teachers", "field", "topics"))
    return save(card, root=root)


def seed_field(root: Optional[Path] = None) -> Dict[str, Any]:
    from skeleton.social.sources import SOTA_POINTERS, catalog
    card = load(root)
    for src in catalog():
        house = str(src.get("house") or "field")[:40]
        rec = (card.get("houses") or {}).get(house) or {"name": house, "seen": 0, "kind": "house"}
        rec["seen"] = int(rec.get("seen") or 0) + 1
        card.setdefault("houses", {})[house] = rec
    for p in SOTA_POINTERS:
        topic = str(p.get("topic") or "")[:80]
        if not topic:
            continue
        rec = (card.get("field") or {}).get(topic) or {"name": topic, "seen": 0, "kind": "field"}
        rec["seen"] = int(rec.get("seen") or 0) + 1
        rec["url"] = str(p.get("url") or "")[:240]
        rec["house"] = str(p.get("house") or "")[:40]
        card.setdefault("field", {})[topic] = rec
    card["n"] = sum(len(card.get(k) or {}) for k in ("houses", "teachers", "field", "topics"))
    return save(card, root=root)
