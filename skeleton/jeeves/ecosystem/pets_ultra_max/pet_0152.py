"""Pet ultra_max 0152.
"""
from __future__ import annotations

ID = "pet_ultra_max_0152"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 152}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
