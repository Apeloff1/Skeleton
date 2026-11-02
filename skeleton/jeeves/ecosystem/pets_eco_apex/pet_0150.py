"""Pet eco_apex 0150.
"""
from __future__ import annotations

ID = "pet_eco_apex_0150"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 150}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
