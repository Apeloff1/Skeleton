"""Pet max 0011.
"""
from __future__ import annotations

ID = "pet_max_0011"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 11}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
