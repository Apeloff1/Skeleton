"""Jeeves + vault + retrieval as operator cards. No secrets. No prose."""
from __future__ import annotations

from typing import Any, Dict, List


def jeeves_card() -> Dict[str, Any]:
    from skeleton.jeeves.core import Jeeves
    j = Jeeves()
    return {
        "kind": "jeeves",
        "laws": list(j.laws)[:8],
        "sessions": len(getattr(j, "_sessions", {}) or {}),
        "era": getattr(j, "era", ""),
        "stored_prose": 0,
    }


def vault_card() -> Dict[str, Any]:
    from skeleton.vault.entropy import EntropyRegistry
    from skeleton.vault.kms import EnvelopeKMS
    from skeleton.vault.keys import KeyRegistry
    reg = EntropyRegistry()
    kms_ok = 0
    keys_n = 0
    try:
        kms = EnvelopeKMS()
        kms_ok = 1
    except Exception:
        kms_ok = 0
    try:
        keys_n = len(KeyRegistry(kms)._versions)
    except Exception:
        keys_n = 0
    return {
        "kind": "vault",
        "entropy": sorted(reg._sources),
        "kms": kms_ok,
        "keys": keys_n,
        "secrets": 0,
        "stored_prose": 0,
    }


def retrieve_card(cue: str = "", *, org=None) -> Dict[str, Any]:
    from skeleton.organism.helix import recall
    from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult
    from skeleton.social.sources import SOTA_POINTERS

    wiki_topics: List[str] = []
    root = None
    if org is not None:
        wiki_topics = list((org.galaxy.mesh.wiki.topics or {}).keys())[:24]
        root = getattr(org, "root", None)
    wiki = [ScoredResult(content="", fragment_id=t, score=1.0 / (i + 1), plane="wiki") for i, t in enumerate(wiki_topics)]
    field = [ScoredResult(content="", fragment_id=p["topic"], score=1.0 / (i + 1), plane="field") for i, p in enumerate(SOTA_POINTERS[:24])]
    helix_hits = recall(cue or "memory", root=root).get("hits") or []
    helix = [ScoredResult(content="", fragment_id=str(h.get("sha") or h.get("topic") or i)[:16], score=float(h.get("score") or 0), plane="helix") for i, h in enumerate(helix_hits)]
    fused = Fuser(FusionStrategy.RRF).fuse({"wiki": wiki, "field": field, "helix": helix}, top_k=8)
    return {
        "kind": "retrieve",
        "cue": (cue or "")[:80],
        "n": len(fused),
        "ids": [r.fragment_id for r in fused],
        "sources": sorted({r.plane for r in fused}),
        "stored_prose": 0,
    }


def satellites_card(org=None, *, cue: str = "") -> Dict[str, Any]:
    from skeleton.organism.quality_state import quality_snapshot
    from skeleton.organism.repair_card import repair_card

    root = getattr(org, "root", None) if org is not None else None
    quality = quality_snapshot(root=root)
    return {
        "kind": "satellites",
        "jeeves": jeeves_card(),
        "vault": vault_card(),
        "retrieve": retrieve_card(cue, org=org),
        "quality": quality,
        "repair_card": repair_card(root=root),
        "stored_prose": 0,
    }
