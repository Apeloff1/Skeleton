"""
Viscera speculative verify and activation steer. Accept-until-mismatch. h becomes h plus alpha u-hat. No torch required in CI.
"""
from __future__ import annotations

import math

from .seam_runtime import admit, stamp

ALPHA = 0.1


def process(data: dict) -> dict:
    refused = admit("specdec_local", data)
    if refused:
        return refused
    if "alpha" in data and data["alpha"] != ALPHA:
        return {"ok": False, "error": "alpha is pinned", "card": "specdec_local", "alpha": ALPHA}
    body: dict = {"alpha": ALPHA}
    if "h" in data or "u" in data:
        height = data.get("h")
        update = data.get("u")
        if (
            isinstance(height, bool)
            or isinstance(update, bool)
            or not isinstance(height, (int, float))
            or not isinstance(update, (int, float))
            or not math.isfinite(float(height))
            or not math.isfinite(float(update))
        ):
            return {
                "ok": False,
                "error": "steer values must be numbers",
                "card": "specdec_local",
                "alpha": ALPHA,
            }
        body["steered"] = float(height) + ALPHA * float(update)
    return stamp("specdec_local", data, body)
