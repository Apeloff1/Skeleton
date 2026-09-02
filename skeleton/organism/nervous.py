"""Nervous system card — SLO budgets + intelligence roster.

Does not run the full orchestrator. Names the five reasoners and
records prose/pressure/helix against house SLOs.
"""
from __future__ import annotations

from typing import Any, Dict


INTELLIGENCE = ("temporal", "causal", "meta", "neurosym", "economic")


def nervous_card(org=None, *, neo=None) -> Dict[str, Any]:
    from skeleton.observability.slo import SLOTracker, ServiceLevelObjective
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.helix import verify as helix_verify
    from skeleton.organism.laws import scan_prose
    from skeleton.organism.organismer import live_organismer

    org = org or live_organismer()
    caps = caps_card()
    prose = scan_prose(org.galaxy.mesh)
    pressure = float(caps.get("pressure") or 0)
    try:
        helix_ok = int(helix_verify(getattr(org, "root", None)).get("ok") or 0)
    except Exception:
        helix_ok = 1
    tracker = SLOTracker()
    tracker.register(ServiceLevelObjective("prose", 1.0))
    tracker.register(ServiceLevelObjective("pressure", 0.90))
    tracker.register(ServiceLevelObjective("helix", 1.0))
    tracker.record("prose", bad=prose > 0)
    tracker.record("pressure", bad=pressure >= 0.90)
    tracker.record("helix", bad=helix_ok != 1)
    slos = {}
    for name in ("prose", "pressure", "helix"):
        slos[name] = {
            "remaining": round(tracker.remaining(name), 4),
            "burn": round(tracker.burn_rate(name), 4),
        }
    teachers = []
    try:
        from skeleton.organism.teachers import slots_of
        teachers = slots_of(neo)
    except Exception:
        teachers = []
    return {
        "kind": "nervous",
        "ok": int(prose == 0 and pressure < 0.90 and helix_ok == 1),
        "slos": slos,
        "intelligence": list(INTELLIGENCE),
        "teachers": teachers,
        "stored_prose": prose,
    }
