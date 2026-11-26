"""
Keep Jeeves import shims and the plan pipeline alive. Lazy doctor, nervous, product.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

SHIMS = ["JeevesCore", "Jeeves"]


def process(data: dict) -> dict:
    refused = admit("jeeves_pipeline", data)
    if refused:
        return refused
    shim = data.get("shim")
    if shim is None:
        return stamp("jeeves_pipeline", data, {"shims": SHIMS})
    if shim not in SHIMS:
        return {
            "ok": False,
            "error": "unknown shim",
            "card": "jeeves_pipeline",
            "shims": list(SHIMS),
        }
    return stamp("jeeves_pipeline", data, {"shims": SHIMS, "shim": shim})
