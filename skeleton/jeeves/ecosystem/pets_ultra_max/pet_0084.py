"""Pet ultra_max 0084.
"""
from __future__ import annotations

ID = "pet_ultra_max_0084"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 84}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
