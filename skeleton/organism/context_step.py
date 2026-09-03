"""Context post-process — five brains, cage, decoder, editor decide.

The original law: memory → compiler → dream → distiller → editor.
Galaxy.pulse is the engine. This module is the organism wrapper so
every pulse, not only org.step, leaves a Hoag-shaped trace.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def run(org, stimulus: str = "", *, sleep: bool = False, neo=None) -> Dict[str, Any]:
    stim = (stimulus or "plan tensor ttk").strip()
    gxy: Dict[str, Any] = {}
    try:
        gxy = org.galaxy.pulse(stim, sleep=sleep)
    except Exception as exc:
        gxy = {"kind": "galaxy-pulse", "error": type(exc).__name__, "stored_prose": 0}
    if not gxy.get("principle"):
        try:
            atom = org.galaxy.distiller.glean(stim)
            gxy["principle"] = atom.to_dict() if atom is not None else None
            if atom is not None:
                ids = list(gxy.get("atom_ids") or [])
                ids.append(atom.id)
                gxy["atom_ids"] = ids
        except Exception:
            pass
    cond: Dict[str, Any] = {}
    try:
        from skeleton.organism.conductor import decide
        cond = decide(org, neo=neo)
    except Exception:
        cond = {}
    cage: Dict[str, Any] = {}
    try:
        from skeleton.galaxy.quarantine import card as cage_card
        cage = cage_card()
    except Exception:
        cage = {}
    return {
        "kind": "context-step",
        "route": gxy.get("route"),
        "atom_ids": gxy.get("atom_ids") or [],
        "pulses": gxy.get("pulses") or 0,
        "decoded": bool(gxy.get("decoded")),
        "audit": gxy.get("audit"),
        "conductor": {"code": cond.get("code"), "why": cond.get("why"), "horizon": cond.get("horizon")},
        "cage": {"denied": cage.get("denied"), "held": cage.get("held")},
        "stored_prose": 0,
    }
