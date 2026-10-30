"""Pet mega 0023.
"""
from __future__ import annotations

ID = "pet_mega_0023"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 23}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
