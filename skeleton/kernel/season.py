"""Kernel season — N orch walks under the profile cap."""
from __future__ import annotations

from typing import Any, Dict, List


def run(text: str = "plan tensor ttk", *, n: int = 0) -> Dict[str, Any]:
    from skeleton.kernel.bank import boot, get

    boot()
    fence = get("sfence")
    if fence is not None and hasattr(fence, "acquire") and not fence.acquire():
        return {"kind": "kernel-season", "walks": 0, "asked": 0, "stopped": "lease", "stored_prose": 0}
    try:
        return _run(text, n=n)
    finally:
        if fence is not None and hasattr(fence, "release"):
            fence.release()


def _run(text: str = "plan tensor ttk", *, n: int = 0) -> Dict[str, Any]:
    from skeleton.kernel.bank import get, live
    from skeleton.kernel.governor import tick as gov_tick
    from skeleton.kernel.orchestrator import Orchestrator
    from skeleton.kernel.profiles import card as profiles_card

    ov = profiles_card().get("overlay") or {}
    walks = n or int(ov.get("walk_n") or 2)
    walks = max(1, min(8, walks))
    orch = get("orch") or Orchestrator()
    traces: List[int] = []
    stopped = ""
    for _ in range(walks):
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
        hold = get("hold")
        if hold is not None and hasattr(hold, "check"):
            if not hold.check(list(live().keys())):
                stopped = "drift"
                break
    return {
        "kind": "kernel-season",
        "walks": len(traces),
        "asked": walks,
        "stages": traces,
        "stopped": stopped,
        "orch": orch.card(),
        "hold": (get("hold").card() if get("hold") is not None else {}),
        "fence": (get("sfence").card() if get("sfence") is not None else {}),
        "stored_prose": 0,
    }
