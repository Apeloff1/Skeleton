"""Pet ultra_max 0177.
"""
from __future__ import annotations

ID = "pet_ultra_max_0177"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 177}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
