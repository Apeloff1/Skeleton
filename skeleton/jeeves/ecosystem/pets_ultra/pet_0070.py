"""Pet ultra 0070.
"""
from __future__ import annotations

ID = "pet_ultra_0070"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 70}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
