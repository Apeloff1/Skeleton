"""Mount eco_apex 0221.
"""
from __future__ import annotations

ID = "mount_eco_apex_0221"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 221}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
