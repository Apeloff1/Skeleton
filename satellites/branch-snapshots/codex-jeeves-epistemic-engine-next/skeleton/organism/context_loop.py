"""Rot-guarded journal + reconstruction forest as one operator loop.

Journal lines become Turns (topic tokens only). RotGuardedCompactor
runs first. Reconstruction forest runs on the same cue. Dream/next
consume the verdict; no article bodies enter the card.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.memory.compaction import Turn
from skeleton.memory.guarded_compaction import RotGuardedCompactor


_COMPACTOR = RotGuardedCompactor()


def turns_from(org, *, root=None) -> List[Turn]:
    from skeleton.organism.journal import tail
    rows = tail(32, root=root if root is not None else getattr(org, "root", None))
    out: List[Turn] = []
    for row in rows or []:
        topic = str(row.get("topic") or row.get("decision") or "step")
        g = row.get("G")
        out.append(Turn(role="step", content=f"{topic} G={g}"))
    for row in list(getattr(org, "log", []) or [])[-16:]:
        topic = str(row.get("topic") or row.get("decision") or "log")
        out.append(Turn(role="log", content=f"{topic} G={row.get('G')}"))
    return out


def assess(org, *, cue: str = "", neo=None, root=None) -> Dict[str, Any]:
    from skeleton.galaxy.graph import reconstruct

    ts = turns_from(org, root=root)
    constraints = ("stored_prose=0", "cite-do-not-copy", "clipped-G")
    guarded = _COMPACTOR.process(ts, constraints=constraints)
    rec = reconstruct(org.galaxy.mesh, cue or "memory graph")
    report = guarded.report.to_dict()
    return {
        "kind": "context-loop",
        "rot": report.get("verdict"),
        "risk": report.get("risk"),
        "compacted": int(guarded.compacted),
        "hint": guarded.hint,
        "turns": len(guarded.turns),
        "forest_n": rec.get("n"),
        "forest_e": rec.get("e"),
        "cue": (cue or "")[:80],
        "stored_prose": 0,
    }


def should_dream(card: Dict[str, Any]) -> bool:
    return str(card.get("rot") or "") == "rot" or int(card.get("compacted") or 0) == 1
