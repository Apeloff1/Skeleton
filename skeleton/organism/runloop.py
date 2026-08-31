"""Bounded pulse walk. Stops on hold/tighten or N steps.

N defaults to 4, hard-capped at 8. Never an unbounded write.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STOP = {"hold", "tighten"}


def rotate_stimulus(i: int, explicit: str = "") -> str:
    if explicit:
        return explicit
    from skeleton.social.sources import SOTA_POINTERS
    row = SOTA_POINTERS[i % len(SOTA_POINTERS)]
    return f"{row['topic']} {row['url']}"


def walk(org=None, *, neo=None, stimulus: str = "", n: int = 4,
         persist: Optional[bool] = None) -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer
    from skeleton.organism.pulse import pulse

    org = org or live_organismer()
    try:
        from skeleton.organism.budget import walk_limit
        from skeleton.organism.caps import live as live_caps
        limit = walk_limit(live_caps().tier, int(n or 4))
    except Exception:
        limit = max(1, min(8, int(n or 4)))
    if not (org.galaxy.mesh.wiki.topics or {}):
        from skeleton.social.seed import seed_field
        seed_field(org.galaxy)
    cards: List[Dict[str, Any]] = []
    used: List[str] = []
    stopped = "cap"
    for i in range(limit):
        stim = rotate_stimulus(i, stimulus)
        used.append(stim.split()[0])
        card = pulse(org, neo=neo, stimulus=stim, persist=persist)
        cards.append({
            "code": (card.get("acted") or {}).get("code"),
            "G": card.get("G"),
        })
        code = str((card.get("acted") or {}).get("code") or "")
        if code in STOP:
            stopped = code
            break
    return {
        "kind": "run",
        "n": len(cards),
        "limit": limit,
        "stopped": stopped,
        "codes": [c["code"] for c in cards],
        "topics": used,
        "G": cards[-1]["G"] if cards else round(org.G, 6),
        "stored_prose": 0,
    }
