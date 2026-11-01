"""Pet ultra_max 0131.
"""
from __future__ import annotations

ID = "pet_ultra_max_0131"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 131}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
