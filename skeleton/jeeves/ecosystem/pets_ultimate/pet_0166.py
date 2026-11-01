"""Pet ultimate 0166.
"""
from __future__ import annotations

ID = "pet_ultimate_0166"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 166}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
