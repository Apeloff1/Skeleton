"""Beyond-step scope — stacked horizons, hardware-capped ambition.

Human-scale next() emits one code. Scope emits a queue across
step / walk / season / decade and writes it to the itinerary.
Ambition shrinks when pressure rises. No forecast theater.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

HORIZONS = ("step", "walk", "season", "decade")
FILL = ("pulse", "dream", "pulse", "contact")


def _ambition(pressure: float) -> int:
    # 0.00 pressure → 12 slots. 0.90+ → 2. Headroom lives below the wall.
    p = max(0.0, min(1.0, float(pressure)))
    return max(2, min(12, int(round((1.0 - p) * 10)) + 2))


def compose(org, *, neo=None) -> Dict[str, Any]:
    from skeleton.organism.chronicle.dump import due as dump_due
    from skeleton.organism.chronicle.itinerary import plan
    from skeleton.organism.next import hint
    from skeleton.organism.path10 import path_card
    from skeleton.organism.sleep import due as sleep_due
    from skeleton.social.coverage import coverage_card

    nxt = hint(org, neo=neo)
    path = path_card(org)
    cov = coverage_card("")
    pressure = float(nxt.get("pressure") or 0)
    n = _ambition(pressure)
    queue: List[str] = [str(nxt.get("code") or "pulse")]
    if sleep_due(org) and "dream" not in queue:
        queue.append("dream")
    if dump_due(getattr(org, "root", None)) and "dump" not in queue:
        queue.append("dump")
    if float(cov.get("score") or 0) < 0.20 and "bind-source" not in queue:
        queue.append("bind-source")
    if float(path.get("mean_step") or 0) < 0.0005 and int(path.get("steps") or 0) >= 3:
        if "contact" not in queue:
            queue.append("contact")
    i = 0
    while len(queue) < n:
        code = FILL[i % len(FILL)]
        queue.append(code)
        i += 1
    planned = plan(queue, root=getattr(org, "root", None), why="scope")
    try:
        from skeleton.organism.chronicle import record
        record(org, {
            "book": "itinerary",
            "topic": "scope " + " ".join(queue[:6]),
            "decision": queue[0],
            "code": queue[0],
            "why": "scope",
            "phase": "plan",
            "G": getattr(org, "G", None),
            "step": getattr(org, "steps", None),
        }, neo=neo)
    except Exception:
        pass
    return {
        "kind": "scope-compose",
        "n": len(queue),
        "queue": queue,
        "planned": planned.get("n"),
        "pressure": pressure,
        "ambition": n,
        "stored_prose": 0,
    }


def card(org=None, *, neo=None) -> Dict[str, Any]:
    from skeleton.organism.chronicle.dump import inventory
    from skeleton.organism.chronicle.itinerary import tail
    from skeleton.organism.next import hint
    from skeleton.organism.organismer import live_organismer
    from skeleton.organism.path10 import path_card

    org = org or live_organismer()
    nxt = hint(org, neo=neo)
    path = path_card(org)
    inv = inventory(getattr(org, "root", None))
    composed = compose(org, neo=neo)
    return {
        "kind": "scope",
        "horizons": list(HORIZONS),
        "G": path.get("G"),
        "target": path.get("target"),
        "toward_10x_pct": path.get("toward_10x_pct"),
        "gap": path.get("gap"),
        "next": nxt.get("code"),
        "queue": composed.get("queue"),
        "ambition": composed.get("ambition"),
        "pressure": composed.get("pressure"),
        "decade": {
            "years": inv.get("years"),
            "dumps": inv.get("n"),
            "horizon_years": inv.get("horizon_years"),
        },
        "itinerary": tail(8, root=getattr(org, "root", None)),
        "stored_prose": 0,
    }


def enact(org=None, *, neo=None) -> Dict[str, Any]:
    """Run the head of the current scope queue through pulse."""
    from skeleton.organism.organismer import live_organismer
    from skeleton.organism.pulse import pulse

    org = org or live_organismer()
    composed = compose(org, neo=neo)
    head = (composed.get("queue") or ["pulse"])[0]
    if head == "dump":
        from skeleton.organism.chronicle.dump import dump
        acted = dump(getattr(org, "root", None), force=True)
    else:
        acted = pulse(org, neo=neo, stimulus="")
    return {
        "kind": "scope-enact",
        "head": head,
        "acted": acted,
        "queue": composed.get("queue"),
        "stored_prose": 0,
    }
