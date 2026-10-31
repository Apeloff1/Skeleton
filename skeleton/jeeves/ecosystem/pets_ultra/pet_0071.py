"""Pet ultra 0071.
"""
from __future__ import annotations

ID = "pet_ultra_0071"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 71}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
