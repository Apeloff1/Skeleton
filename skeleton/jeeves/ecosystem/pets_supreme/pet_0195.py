"""Pet supreme 0195.
"""
from __future__ import annotations

ID = "pet_supreme_0195"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 195}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
