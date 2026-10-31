"""Pet ultra 0078.
"""
from __future__ import annotations

ID = "pet_ultra_0078"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 78}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
