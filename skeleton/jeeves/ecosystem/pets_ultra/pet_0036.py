"""Pet ultra 0036.
"""
from __future__ import annotations

ID = "pet_ultra_0036"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 36}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
