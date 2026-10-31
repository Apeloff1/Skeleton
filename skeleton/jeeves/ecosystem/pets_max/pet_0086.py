"""Pet max 0086.
"""
from __future__ import annotations

ID = "pet_max_0086"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 86}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
