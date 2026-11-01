"""Pet ultimate 0234.
"""
from __future__ import annotations

ID = "pet_ultimate_0234"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 234}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
