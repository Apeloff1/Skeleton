"""Pet ultimate 0216.
"""
from __future__ import annotations

ID = "pet_ultimate_0216"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 216}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
