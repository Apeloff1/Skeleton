"""Pet ultra 0033.
"""
from __future__ import annotations

ID = "pet_ultra_0033"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 33}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
