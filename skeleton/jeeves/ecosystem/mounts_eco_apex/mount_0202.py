"""Mount eco_apex 0202.
"""
from __future__ import annotations

ID = "mount_eco_apex_0202"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 202}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
