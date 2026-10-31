"""Pet max 0082.
"""
from __future__ import annotations

ID = "pet_max_0082"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 82}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
