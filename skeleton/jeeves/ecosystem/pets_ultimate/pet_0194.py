"""Pet ultimate 0194.
"""
from __future__ import annotations

ID = "pet_ultimate_0194"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 194}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
