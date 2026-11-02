"""Pet eco_supreme 0205.
"""
from __future__ import annotations

ID = "pet_eco_supreme_0205"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 205}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
