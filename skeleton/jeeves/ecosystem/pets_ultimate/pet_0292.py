"""Pet ultimate 0292.
"""
from __future__ import annotations

ID = "pet_ultimate_0292"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 292}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
