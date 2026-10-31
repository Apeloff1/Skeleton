"""Pet ultra 0049.
"""
from __future__ import annotations

ID = "pet_ultra_0049"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 49}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
