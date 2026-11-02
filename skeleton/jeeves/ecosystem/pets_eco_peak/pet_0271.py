"""Pet eco_peak 0271.
"""
from __future__ import annotations

ID = "pet_eco_peak_0271"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 271}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
