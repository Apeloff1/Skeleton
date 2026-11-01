"""Pet ultimate 0173.
"""
from __future__ import annotations

ID = "pet_ultimate_0173"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 173}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
