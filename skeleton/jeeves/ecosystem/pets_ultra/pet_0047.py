"""Pet ultra 0047.
"""
from __future__ import annotations

ID = "pet_ultra_0047"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 47}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
