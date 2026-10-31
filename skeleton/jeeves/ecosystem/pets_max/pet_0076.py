"""Pet max 0076.
"""
from __future__ import annotations

ID = "pet_max_0076"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 76}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
