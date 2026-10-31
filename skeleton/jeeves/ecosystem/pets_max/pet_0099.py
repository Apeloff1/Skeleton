"""Pet max 0099.
"""
from __future__ import annotations

ID = "pet_max_0099"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
