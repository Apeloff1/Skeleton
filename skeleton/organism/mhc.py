"""MHC card — last magnitude / hebb / compression from Genos history."""
from __future__ import annotations

from typing import Any, Dict


def mhc_card(org) -> Dict[str, Any]:
    hist = list(getattr(org.genos, "history", []) or [])
    last = hist[-1] if hist else {}
    return {
        "kind": "mhc",
        "M": last.get("M"),
        "H": last.get("H"),
        "C": last.get("C"),
        "S": last.get("S"),
        "epsilon": last.get("epsilon") or last.get("eps"),
        "growth": last.get("growth"),
        "G": round(float(org.G), 6),
        "pulses": int(getattr(org.genos, "pulses", 0) or 0),
        "stored_prose": 0,
    }
