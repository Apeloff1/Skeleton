"""Pet eco_apex 0375.
"""
from __future__ import annotations

ID = "pet_eco_apex_0375"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 375}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
