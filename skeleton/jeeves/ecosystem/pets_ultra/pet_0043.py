"""Pet ultra 0043.
"""
from __future__ import annotations

ID = "pet_ultra_0043"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 43}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
