"""
Enforce clipped-G and snowball mass. G grows only through MHC times S with clips. Mass per forge at most prior times 1.1.
"""
from __future__ import annotations

import math

from .seam_runtime import admit, stamp

CLIP = 1.1


def process(data: dict) -> dict:
    refused = admit("clipped_mass", data)
    if refused:
        return refused
    growth = data.get("growth", CLIP)
    if (
        isinstance(growth, bool)
        or not isinstance(growth, (int, float))
        or not math.isfinite(float(growth))
        or not 0 < float(growth) <= CLIP
    ):
        return {
            "ok": False,
            "error": "growth exceeds the clip",
            "card": "clipped_mass",
            "clip": CLIP,
        }
    return stamp("clipped_mass", data, {"clip": CLIP, "growth": float(growth)})
