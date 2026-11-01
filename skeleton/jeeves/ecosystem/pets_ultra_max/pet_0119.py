"""Pet ultra_max 0119.
"""
from __future__ import annotations

ID = "pet_ultra_max_0119"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 119}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
