"""Pet max 0059.
"""
from __future__ import annotations

ID = "pet_max_0059"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 59}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
