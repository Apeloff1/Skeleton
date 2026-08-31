"""Operator next — one coded hint, not a plan essay.

Priority: pressure → freshness → coverage → growth stall → pulse.
"""
from __future__ import annotations

from typing import Any, Dict


def hint(org, *, neo=None) -> Dict[str, Any]:
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.path10 import path_card
    from skeleton.social.coverage import coverage_card

    caps = caps_card()
    path = path_card(org)
    cov = coverage_card("")
    fresh = org.galaxy.editor.freshness()
    pressure = float(caps.get("pressure") or 0)
    if pressure >= 0.75:
        code, why = "tighten", "pressure"
    elif int(fresh.get("stale_n") or 0) >= 4:
        code, why = "dream", "stale-index"
    elif float(cov.get("score") or 0) < 0.20 and not cov.get("bound"):
        code, why = "bind-source", "coverage"
    elif float(path.get("mean_step") or 0) < 0.0005 and int(path.get("steps") or 0) >= 3:
        code, why = "contact", "stall"
    elif float(path.get("gap") or 0) <= 0.05:
        code, why = "hold", "at-target"
    else:
        code, why = "pulse", "gap"
    return {
        "kind": "next",
        "code": code,
        "why": why,
        "pressure": pressure,
        "coverage": cov.get("score"),
        "gap": path.get("gap"),
        "stale_n": fresh.get("stale_n"),
        "stored_prose": 0,
    }
