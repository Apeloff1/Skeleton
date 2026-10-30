"""Pet mega 0004.
"""
from __future__ import annotations

ID = "pet_mega_0004"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 4}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
