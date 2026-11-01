"""Pet ultimate 0217.
"""
from __future__ import annotations

ID = "pet_ultimate_0217"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 217}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
