"""Operator-facing quality state helpers.

Provides a compact rollup shape so product, nervous, doctor, and satellites
can speak about quality in one vocabulary even when only some subsystems
have emitted explicit quality reports so far.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


def summarize_quality(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = [dict(x) for x in items if x]
    if not rows:
        return {
            "kind": "quality-rollup",
            "count": 0,
            "accepted": 0,
            "rejected": 0,
            "accept_rate": 0.0,
            "weakest": "",
            "reasons": {},
        }
    accepted = sum(1 for x in rows if x.get("accepted"))
    rejected = len(rows) - accepted
    weakest = min(rows, key=lambda x: float(x.get("score", 0.0) or 0.0))
    reasons: Dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "kind": "quality-rollup",
        "count": len(rows),
        "accepted": accepted,
        "rejected": rejected,
        "accept_rate": round(accepted / max(1, len(rows)), 4),
        "weakest": weakest.get("weakest_path") or weakest.get("path") or "",
        "reasons": reasons,
    }


def quality_pressure(rollup: Dict[str, Any]) -> float:
    rejected = int(rollup.get("rejected") or 0)
    count = int(rollup.get("count") or 0)
    return round(rejected / max(1, count), 4)
