"""Median Absolute Deviation filter for principle contradiction.

Math, not an LLM. Two passes:

1. Pairwise Jaccard on principle tokens. Jaccard ≥ 0.50 → same claim;
   keep the higher-confidence atom, supersede the other.
2. Robust z on confidences. z = |x - median| / (1.4826 * MAD).
   z > 3.0 and x below the median → weak outlier, supersede.

No antonym tables. No teacher call.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

from skeleton.galaxy.atoms import Atom, jaccard


def _median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return ys[mid]
    return 0.5 * (ys[mid - 1] + ys[mid])


def mad(xs: Sequence[float]) -> Tuple[float, float]:
    med = _median(xs)
    return med, _median([abs(x - med) for x in xs])


def robust_z(x: float, med: float, scatter: float) -> float:
    denom = 1.4826 * scatter if scatter > 1e-9 else 1.0
    return abs(x - med) / denom


def audit(principles: Iterable[Atom], *, jaccard_cut: float = 0.50, z_cut: float = 3.0) -> Dict[str, Any]:
    rules: List[Atom] = [a for a in principles if a and not a.superseded_by]
    pairs = 0
    killed = 0
    for i, a in enumerate(rules):
        for b in rules[i + 1 :]:
            if a.superseded_by or b.superseded_by:
                continue
            score = jaccard(a.tokens, b.tokens)
            if score < jaccard_cut:
                continue
            pairs += 1
            winner, loser = (a, b) if a.confidence >= b.confidence else (b, a)
            loser.superseded_by = winner.id
            killed += 1
    alive = [a for a in rules if not a.superseded_by]
    confs = [float(a.confidence) for a in alive]
    med, scatter = mad(confs)
    outliers = 0
    for a in alive:
        z = robust_z(float(a.confidence), med, scatter)
        if z > z_cut and float(a.confidence) < med:
            a.superseded_by = "mad-outlier"
            outliers += 1
            killed += 1
    return {
        "kind": "mad-audit",
        "seen": len(rules),
        "pairs": pairs,
        "killed": killed,
        "outliers": outliers,
        "median": round(med, 4),
        "mad": round(scatter, 4),
        "alive": sum(1 for a in rules if not a.superseded_by),
        "stored_prose": 0,
    }
