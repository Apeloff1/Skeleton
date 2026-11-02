"""Pet eco_supreme 0099.
"""
from __future__ import annotations

ID = "pet_eco_supreme_0099"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
