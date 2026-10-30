"""Pet mega 0015.
"""
from __future__ import annotations

ID = "pet_mega_0015"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 15}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
