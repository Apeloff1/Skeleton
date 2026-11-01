"""Pet ultimate 0248.
"""
from __future__ import annotations

ID = "pet_ultimate_0248"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 248}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
