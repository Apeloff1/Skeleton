"""Pet mega 0010.
"""
from __future__ import annotations

ID = "pet_mega_0010"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 10}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
