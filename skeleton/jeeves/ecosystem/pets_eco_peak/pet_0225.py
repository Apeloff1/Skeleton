"""Pet eco_peak 0225.
"""
from __future__ import annotations

ID = "pet_eco_peak_0225"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 225}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
