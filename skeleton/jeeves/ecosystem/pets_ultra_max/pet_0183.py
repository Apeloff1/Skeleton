"""Pet ultra_max 0183.
"""
from __future__ import annotations

ID = "pet_ultra_max_0183"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 183}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
