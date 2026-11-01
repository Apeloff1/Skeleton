"""Pet ultimate 0111.
"""
from __future__ import annotations

ID = "pet_ultimate_0111"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 111}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
