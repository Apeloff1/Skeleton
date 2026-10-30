"""Pet mega 0034.
"""
from __future__ import annotations

ID = "pet_mega_0034"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 34}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
