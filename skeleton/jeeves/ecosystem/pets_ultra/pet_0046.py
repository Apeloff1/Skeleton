"""Pet ultra 0046.
"""
from __future__ import annotations

ID = "pet_ultra_0046"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 46}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
