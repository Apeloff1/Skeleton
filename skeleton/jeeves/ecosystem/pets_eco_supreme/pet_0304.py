"""Pet eco_supreme 0304.
"""
from __future__ import annotations

ID = "pet_eco_supreme_0304"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 304}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
