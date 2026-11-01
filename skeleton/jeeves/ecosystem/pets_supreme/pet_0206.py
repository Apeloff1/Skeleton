"""Pet supreme 0206.
"""
from __future__ import annotations

ID = "pet_supreme_0206"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 206}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
