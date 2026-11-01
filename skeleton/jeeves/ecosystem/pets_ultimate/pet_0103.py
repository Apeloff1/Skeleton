"""Pet ultimate 0103.
"""
from __future__ import annotations

ID = "pet_ultimate_0103"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
