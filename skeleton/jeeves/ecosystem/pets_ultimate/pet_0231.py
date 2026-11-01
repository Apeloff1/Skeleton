"""Pet ultimate 0231.
"""
from __future__ import annotations

ID = "pet_ultimate_0231"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 231}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
