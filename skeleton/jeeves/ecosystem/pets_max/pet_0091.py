"""Pet max 0091.
"""
from __future__ import annotations

ID = "pet_max_0091"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 91}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
