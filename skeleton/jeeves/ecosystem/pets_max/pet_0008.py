"""Pet max 0008.
"""
from __future__ import annotations

ID = "pet_max_0008"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 8}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
