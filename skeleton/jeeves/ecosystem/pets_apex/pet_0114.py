"""Pet apex 0114.
"""
from __future__ import annotations

ID = "pet_apex_0114"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 114}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
