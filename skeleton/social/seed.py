"""Seed field pointers into the wiki as citation atoms.

Idempotent. Topic already in the nucleus → skip. Bodies stay on the
far side of the URL.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.social.sources import SOTA_POINTERS


def seed_field(galaxy) -> Dict[str, Any]:
    minted = skipped = 0
    for row in SOTA_POINTERS:
        topic = str(row["topic"])
        if topic in (galaxy.mesh.wiki.topics or {}):
            skipped += 1
            continue
        atom = galaxy.codec.encode(
            topic,
            kind="citation",
            brain="editor",
            citation=str(row.get("url") or ""),
            url=str(row.get("url") or ""),
            depth_hint=5,
            tags=("field", str(row.get("house") or "")),
        )
        galaxy.editor.index_topic(atom)
        galaxy.mesh.wiki.topics[topic] = str(row.get("url") or "")[:240]
        minted += 1
    card = {
        "kind": "field-seed",
        "minted": minted,
        "skipped": skipped,
        "pointers": len(SOTA_POINTERS),
        "wiki_topics": len(galaxy.mesh.wiki.topics),
        "stored_prose": 0,
    }
    try:
        from skeleton.organism.chronicle import seed as chronicle_seed
        from skeleton.organism.organismer import live_organismer
        card["rolodex"] = chronicle_seed(live_organismer())
    except Exception:
        pass
    return card
