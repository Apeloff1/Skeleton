"""Pet supreme 0249.
"""
from __future__ import annotations

ID = "pet_supreme_0249"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 249}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
