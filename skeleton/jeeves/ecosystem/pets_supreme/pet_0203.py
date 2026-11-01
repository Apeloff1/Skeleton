"""Pet supreme 0203.
"""
from __future__ import annotations

ID = "pet_supreme_0203"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 203}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
