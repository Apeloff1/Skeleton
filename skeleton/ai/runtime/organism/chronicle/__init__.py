"""Chronicle traffic control — one write fans out to the right books.

Hot: journal + helix + ledger (already persist-owned).
Cold: annals monthly rolls.
Who: rolodex.
Where-next: itinerary.
Find: inverted index.
Decade: dump/rotate when a hot book exceeds HOT_BYTES.

Eidetic here means hashed handles and compact cards, not article bodies.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.organism.chronicle import annals, dump, index, itinerary, rolodex
from skeleton.organism.chronicle.books import HORIZON_YEARS, HOT_BYTES


def record(org, event: Dict[str, Any], *, neo=None) -> Dict[str, Any]:
    root = getattr(org, "root", None)
    topic = str(event.get("topic") or event.get("decision") or event.get("code") or "")[:120]
    decision = str(event.get("decision") or event.get("code") or "")[:80]
    code = str(event.get("code") or event.get("decision") or "")[:40]
    rolled = rolodex.see("topic", topic or "step", meta={"url": event.get("url")}, root=root)
    if event.get("house"):
        rolodex.see("house", str(event.get("house"))[:40], root=root)
    if neo is not None:
        try:
            from skeleton.organism.teachers import slots_of
            for slot in slots_of(neo):
                rolodex.see("teacher", slot, root=root)
        except Exception:
            pass
    walked = itinerary.append({
        "code": code, "why": event.get("why") or "record",
        "phase": event.get("phase") or "walk",
        "step": event.get("step") or getattr(org, "steps", None),
        "G": event.get("G") or getattr(org, "G", None),
    }, root=root)
    cold = annals.write({
        "book": event.get("book") or "journal",
        "topic": topic, "decision": decision, "code": code,
        "G": event.get("G") or getattr(org, "G", None),
        "sha": event.get("sha") or "",
        "at": event.get("at"),
    }, root=root)
    idx = index.add(topic or code, book=str(event.get("book") or "journal"),
                    ref=str(walked.get("at") or cold.get("path") or topic), root=root)
    dumped = dump.dump(root) if dump.due(root) else {"n": 0, "rotated": []}
    return {
        "kind": "chronicle",
        "rolodex_n": rolled.get("n"),
        "itinerary_at": walked.get("at"),
        "annals": {"year": cold.get("year"), "month": cold.get("month")},
        "index_n": idx.get("n"),
        "dump": dumped,
        "stored_prose": 0,
    }


def card(org=None, *, cue: str = "") -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer
    org = org or live_organismer()
    root = getattr(org, "root", None)
    rolo = rolodex.load(root)
    return {
        "kind": "chronicle",
        "horizon_years": HORIZON_YEARS,
        "hot_bytes": HOT_BYTES,
        "rolodex_n": rolo.get("n"),
        "houses": sorted((rolo.get("houses") or {}).keys())[:12],
        "itinerary": itinerary.tail(6, root=root),
        "index": index.lookup(cue or "memory", root=root),
        "dump": dump.inventory(root),
        "annals_years": annals.years(root=root),
        "stored_prose": 0,
    }


def seed(org=None) -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer
    org = org or live_organismer()
    root = getattr(org, "root", None)
    return rolodex.seed_field(root)
