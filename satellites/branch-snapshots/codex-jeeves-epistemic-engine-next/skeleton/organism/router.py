"""Dual-layer write router — house analog of fast-route / slow-consolidate.

Field paper (cite, do not copy method body): arXiv 2608.22215.
House rule is math on token Jaccard against the wiki nucleus:

    skip   ≥ 0.72  already held
    update ≥ 0.38  same topic, refresh citation
    new    else    mint

Slow path is DreamBrain.sleep, not SFT. No teacher weights on this shelf.
"""
from __future__ import annotations

from typing import Dict, Iterable, Tuple

from skeleton.galaxy.atoms import jaccard, token_set

SKIP, UPDATE, NEW = "skip", "update", "new"


def route(stimulus: str, topics: Iterable[str]) -> Tuple[str, float, str]:
    src = token_set(stimulus or "")
    best = 0.0
    hit = ""
    for topic in topics:
        score = jaccard(src, token_set(str(topic)))
        if score > best:
            best, hit = score, str(topic)
    if best >= 0.72:
        return SKIP, best, hit
    if best >= 0.38:
        return UPDATE, best, hit
    return NEW, best, hit


def should_pulse(decision: str) -> bool:
    return decision in {NEW, UPDATE}


def card(decision: str, score: float, hit: str) -> Dict[str, object]:
    return {
        "kind": "write-route",
        "decision": decision,
        "score": round(float(score), 4),
        "hit": hit[:80],
        "cite": "https://arxiv.org/abs/2608.22215",
        "stored_prose": 0,
    }
