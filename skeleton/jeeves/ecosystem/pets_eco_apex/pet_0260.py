"""Pet eco_apex 0260.
"""
from __future__ import annotations

ID = "pet_eco_apex_0260"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 260}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
