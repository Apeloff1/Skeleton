"""Pet ultimate 0187.
"""
from __future__ import annotations

ID = "pet_ultimate_0187"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 187}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
