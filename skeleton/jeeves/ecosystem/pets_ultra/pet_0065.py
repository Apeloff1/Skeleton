"""Pet ultra 0065.
"""
from __future__ import annotations

ID = "pet_ultra_0065"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 65}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
