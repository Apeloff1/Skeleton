"""Kernel season — N orch walks under the profile cap."""
from __future__ import annotations

from typing import Any, Dict, List


def run(text: str = "plan tensor ttk", *, n: int = 0) -> Dict[str, Any]:
    from skeleton.kernel.bank import boot, get
    from skeleton.kernel.governor import tick as gov_tick
    from skeleton.kernel.orchestrator import Orchestrator
    from skeleton.kernel.profiles import card as profiles_card

    boot()
    ov = profiles_card().get("overlay") or {}
    walks = n or int(ov.get("walk_n") or 2)
    walks = max(1, min(8, walks))
    orch = get("orch") or Orchestrator()
    traces: List[int] = []
    stopped = ""
    for i in range(walks):
        gov = gov_tick()
        if float(gov.get("pressure") or 0) >= 0.90:
            stopped = "pressure"
            break
        slo = get("slo")
        if slo is not None and hasattr(slo, "trip") and slo.trip():
            stopped = "slo"
            break
        card = orch.dispatch(text)
        traces.append(int(card.get("n") or 0))
    return {
        "kind": "kernel-season",
        "walks": len(traces),
        "asked": walks,
        "stages": traces,
        "stopped": stopped,
        "orch": orch.card(),
        "stored_prose": 0,
    }
