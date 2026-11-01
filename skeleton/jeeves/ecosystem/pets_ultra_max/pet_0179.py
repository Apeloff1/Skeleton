"""Pet ultra_max 0179.
"""
from __future__ import annotations

ID = "pet_ultra_max_0179"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 179}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
