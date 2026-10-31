"""Pet ultra 0064.
"""
from __future__ import annotations

ID = "pet_ultra_0064"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 64}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
