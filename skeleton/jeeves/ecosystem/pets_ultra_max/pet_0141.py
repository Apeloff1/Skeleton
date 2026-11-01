"""Pet ultra_max 0141.
"""
from __future__ import annotations

ID = "pet_ultra_max_0141"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 141}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
