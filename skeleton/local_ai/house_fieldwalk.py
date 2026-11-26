"""
Bind the 27-repo Apeloff1 house as pointer atoms, balance fieldwalk across houses, and run speculative RAG prefetch without storing prose.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

HOUSES = 27


def process(data: dict) -> dict:
    refused = admit("house_fieldwalk", data)
    if refused:
        return refused
    house = data.get("house")
    if house is None:
        return stamp("house_fieldwalk", data, {"houses": HOUSES})
    if isinstance(house, bool) or not isinstance(house, int) or not 1 <= house <= HOUSES:
        return {
            "ok": False,
            "error": "house is out of range",
            "card": "house_fieldwalk",
            "houses": HOUSES,
        }
    return stamp("house_fieldwalk", data, {"houses": HOUSES, "house": house})
