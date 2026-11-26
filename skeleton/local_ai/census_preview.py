"""
Treat the Preview census as inventory law. 3893 entries at 006e878. Do not recount by dumping trees.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

CENSUS = 3893


def process(data: dict) -> dict:
    refused = admit("census_preview", data)
    if refused:
        return refused
    if "count" in data and data["count"] != CENSUS:
        return {
            "ok": False,
            "error": "census is pinned",
            "card": "census_preview",
            "census": CENSUS,
        }
    return stamp("census_preview", data, {"census": CENSUS})
