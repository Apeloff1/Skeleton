"""Pet eco_supreme 0180.
"""
from __future__ import annotations

ID = "pet_eco_supreme_0180"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 180}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
