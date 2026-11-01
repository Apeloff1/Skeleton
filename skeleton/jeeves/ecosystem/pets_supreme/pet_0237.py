"""Pet supreme 0237.
"""
from __future__ import annotations

ID = "pet_supreme_0237"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 237}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
