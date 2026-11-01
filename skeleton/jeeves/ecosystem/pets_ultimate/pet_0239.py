"""Pet ultimate 0239.
"""
from __future__ import annotations

ID = "pet_ultimate_0239"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 239}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
