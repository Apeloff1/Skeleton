"""Pet ultra_max 0197.
"""
from __future__ import annotations

ID = "pet_ultra_max_0197"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 197}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
