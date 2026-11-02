"""Pet eco_peak 0263.
"""
from __future__ import annotations

ID = "pet_eco_peak_0263"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 263}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
