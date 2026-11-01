"""Pet ultimate 0284.
"""
from __future__ import annotations

ID = "pet_ultimate_0284"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 284}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
