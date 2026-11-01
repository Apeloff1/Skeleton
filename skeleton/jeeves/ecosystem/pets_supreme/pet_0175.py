"""Pet supreme 0175.
"""
from __future__ import annotations

ID = "pet_supreme_0175"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 175}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
