"""Pet mega 0029.
"""
from __future__ import annotations

ID = "pet_mega_0029"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 29}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
