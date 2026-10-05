"""Week — two days then dump. Decade backup gets a live producer."""
from __future__ import annotations

from typing import Any, Dict, List


def run(org=None, *, days: int = 2, neo=None) -> Dict[str, Any]:
    from skeleton.organism.chronicle.dump import dump
    from skeleton.organism.day import run as day_run
    from skeleton.organism.organismer import live_organismer

    org = org or live_organismer()
    days = max(1, min(3, int(days)))
    rows: List[Dict[str, Any]] = []
    stopped = ""
    for i in range(days):
        card = day_run(org, n=1, neo=neo)
        rows.append({"i": i, "heads": card.get("heads"), "stopped": card.get("stopped")})
        if card.get("stopped") == "pressure":
            stopped = "pressure"
            break
    dumped = dump(getattr(org, "root", None), force=True)
    return {
        "kind": "week",
        "days": len(rows),
        "asked": days,
        "rows": rows,
        "stopped": stopped,
        "dump": {"n": dumped.get("n"), "rotated": dumped.get("rotated")},
        "field": __import__("skeleton.organism.runloop", fromlist=["bound_card"]).bound_card(getattr(org, "root", None)),
        "stored_prose": 0,
    }
