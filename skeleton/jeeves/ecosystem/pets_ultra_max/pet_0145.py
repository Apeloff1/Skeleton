"""Pet ultra_max 0145.
"""
from __future__ import annotations

ID = "pet_ultra_max_0145"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 145}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
