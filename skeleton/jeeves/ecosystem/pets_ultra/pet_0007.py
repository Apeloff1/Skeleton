"""Pet ultra 0007.
"""
from __future__ import annotations

ID = "pet_ultra_0007"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 7}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
