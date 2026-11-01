"""Pet ultimate 0288.
"""
from __future__ import annotations

ID = "pet_ultimate_0288"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 288}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
