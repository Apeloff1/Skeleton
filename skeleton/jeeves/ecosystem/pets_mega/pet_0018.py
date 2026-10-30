"""Pet mega 0018.
"""
from __future__ import annotations

ID = "pet_mega_0018"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 18}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
