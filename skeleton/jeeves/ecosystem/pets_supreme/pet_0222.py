"""Pet supreme 0222.
"""
from __future__ import annotations

ID = "pet_supreme_0222"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 222}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
