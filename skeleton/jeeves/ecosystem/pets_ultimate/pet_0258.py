"""Pet ultimate 0258.
"""
from __future__ import annotations

ID = "pet_ultimate_0258"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 258}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
