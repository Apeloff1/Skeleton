"""Pet max 0083.
"""
from __future__ import annotations

ID = "pet_max_0083"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 83}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
