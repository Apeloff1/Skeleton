"""Pet ultimate 0268.
"""
from __future__ import annotations

ID = "pet_ultimate_0268"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 268}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
