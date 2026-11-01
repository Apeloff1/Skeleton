"""Pet ultimate 0090.
"""
from __future__ import annotations

ID = "pet_ultimate_0090"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 90}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
