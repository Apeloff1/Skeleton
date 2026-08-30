"""Improve — "like Elden Ring" raises the house, not a copy of the game.

Aspects that move: neo/rms ppl, steps, genos G, era dialect, mix heads.
Aspects that must not move: third-party prose, secrets, assets.
Order-of-magnitude is the trajectory target. Laws gate every write.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from skeleton.cortex.antiplag import distill_dialect, guard
from skeleton.cortex.laws import LawError, check
from skeleton.cortex.refs import lookup, record_provenance

_LIKE = re.compile(r"\blike\s+(.+)$", re.I)

ASPECTS = {
    "soulslike": (
        "soulslike ttk elite dread bonfire rest extraction heat",
        "plan tensor hp dps stagger posture",
        "walk fog gate elite pack trash mix",
    ),
    "roguelike": (
        "roguelike lattice mix trash elite boss seed",
        "plan tensor ttk heat run reset",
        "shop relic floor climb",
    ),
    "metroidvania": (
        "metroidvania backtrack map lock key",
        "plan tensor exploration pack ability gate",
        "room graph traversal",
    ),
    "extraction_now": (
        "extraction_now ttk elite dread extract extract",
        "plan tensor loot heat zone timer",
        "squad wipe extract window",
    ),
    "cozy": (
        "cozy harvest era crop season",
        "plan tensor day cycle gift",
        "town route rest",
    ),
    "cozy_wholesome": (
        "cozy harvest era crop season",
        "plan tensor day cycle gift",
        "town route rest",
    ),
}


def _aspects(era: str, title: str) -> List[str]:
    pack = list(ASPECTS.get(era, ASPECTS["soulslike"]))
    pack.append(distill_dialect(title, era))
    return pack


def improve(neo, stimulus: str, *, rounds: int = 16) -> Dict[str, Any]:
    stim = stimulus or ""
    ref = lookup(stim)
    if ref is None:
        m = _LIKE.search(stim)
        if m:
            ref = lookup(m.group(1))
    if ref is None:
        return {"improved": 0, "reason": "no-reference", "law": "cite-do-not-copy"}

    era = str(ref.get("era") or "soulslike")
    title = str(ref.get("title") or "")
    texts = _aspects(era, title)
    for t in texts:
        try:
            guard(t, title)
        except LawError as exc:
            return {"improved": 0, "reason": str(exc), "law": exc.law}

    check({"kind": "improve", "dialect": texts[0], "title": title, "era": era})

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    before = {
        "G": float(getattr(getattr(neo, "genos_engine", None), "G", 1.0) or 1.0),
        "neo_steps": int(getattr(xf, "steps", 0) or 0),
        "rms_steps": int(getattr(rms, "steps", 0) or 0),
    }
    if xf is not None:
        for _ in range(max(4, int(rounds))):
            xf.fit(texts, lr=0.05, schedule="cosine")
    if rms is not None:
        for _ in range(max(2, int(rounds) // 2)):
            rms.fit(texts, lr=0.05, schedule="cosine")
    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        xf_s = getattr(port, "transformer", None)
        if xf_s is not None and hasattr(xf_s, "fit"):
            xf_s.fit(texts[:2], lr=0.04, schedule="cosine")

    pulses = []
    if hasattr(neo, "genos"):
        for _ in range(8):
            pulses.append(neo.genos(" ".join(texts)[:180]))

    record_provenance({**ref, "dialect": texts[-1]}, action="improve")
    after_g = float(getattr(getattr(neo, "genos_engine", None), "G", before["G"]) or before["G"])
    ratio = after_g / max(before["G"], 1e-9)
    card = check({
        "kind": "improve",
        "improved": 1,
        "title": title,
        "era": era,
        "url": ref.get("url"),
        "citation": ref.get("citation"),
        "stored_prose": 0,
        "law": "ok",
        "rounds": int(rounds),
        "G0": round(before["G"], 6),
        "G": round(after_g, 6),
        "ratio": round(ratio, 4),
        "target": 10.0,
        "neo_steps": int(getattr(xf, "steps", 0) or 0) - before["neo_steps"],
        "rms_steps": int(getattr(rms, "steps", 0) or 0) - before["rms_steps"],
        "epsilon": float(getattr(getattr(neo, "genos_engine", None), "epsilon", 0) or 0),
        "dialect": texts[-1],
    })
    return card
