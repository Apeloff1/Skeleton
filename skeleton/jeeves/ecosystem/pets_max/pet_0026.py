"""Pet max 0026.
"""
from __future__ import annotations

ID = "pet_max_0026"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 26}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
