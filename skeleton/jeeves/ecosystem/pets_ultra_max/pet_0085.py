"""Pet ultra_max 0085.
"""
from __future__ import annotations

ID = "pet_ultra_max_0085"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 85}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
