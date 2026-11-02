"""Pet eco_supreme 0122.
"""
from __future__ import annotations

ID = "pet_eco_supreme_0122"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 122}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
