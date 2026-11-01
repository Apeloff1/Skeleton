"""Pet ultimate 0295.
"""
from __future__ import annotations

ID = "pet_ultimate_0295"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 295}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
