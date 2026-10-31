"""Pet ultra 0006.
"""
from __future__ import annotations

ID = "pet_ultra_0006"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 6}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
