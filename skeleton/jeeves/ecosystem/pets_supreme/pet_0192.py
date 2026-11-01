"""Pet supreme 0192.
"""
from __future__ import annotations

ID = "pet_supreme_0192"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 192}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
