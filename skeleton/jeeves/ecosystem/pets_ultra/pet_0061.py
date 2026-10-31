"""Pet ultra 0061.
"""
from __future__ import annotations

ID = "pet_ultra_0061"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 61}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
