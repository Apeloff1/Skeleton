"""Pet max 0095.
"""
from __future__ import annotations

ID = "pet_max_0095"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 95}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
