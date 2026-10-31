"""Mount apex 0111.
"""
from __future__ import annotations

ID = "mount_apex_0111"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 111}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
