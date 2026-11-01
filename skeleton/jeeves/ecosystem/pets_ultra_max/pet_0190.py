"""Pet ultra_max 0190.
"""
from __future__ import annotations

ID = "pet_ultra_max_0190"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 190}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
