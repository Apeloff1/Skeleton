"""Pet ultra_max 0031.
"""
from __future__ import annotations

ID = "pet_ultra_max_0031"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 31}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
