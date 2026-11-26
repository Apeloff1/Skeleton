"""
Four-axis critique on improve and four-cell cockpit Monte Carlo. Cut sets era. Do not retune live knobs without doctor.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

AXES = ["fun", "clarity", "feasibility", "originality"]


def process(data: dict) -> dict:
    refused = admit("critique_cockpit", data)
    if refused:
        return refused
    axis = data.get("axis")
    if axis is None:
        return stamp("critique_cockpit", data, {"axes": AXES})
    if axis not in AXES:
        return {
            "ok": False,
            "error": "unknown axis",
            "card": "critique_cockpit",
            "axes": list(AXES),
        }
    return stamp("critique_cockpit", data, {"axes": AXES, "axis": axis})
