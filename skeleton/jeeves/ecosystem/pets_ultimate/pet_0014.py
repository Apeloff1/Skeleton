"""Pet ultimate 0014.
"""
from __future__ import annotations

ID = "pet_ultimate_0014"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 14}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
