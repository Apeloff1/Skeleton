"""Pet mega 0002.
"""
from __future__ import annotations

ID = "pet_mega_0002"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 2}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
