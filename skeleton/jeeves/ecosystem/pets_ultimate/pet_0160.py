"""Pet ultimate 0160.
"""
from __future__ import annotations

ID = "pet_ultimate_0160"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 160}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
