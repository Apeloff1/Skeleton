"""Mount ultimate 0241.
"""
from __future__ import annotations

ID = "mount_ultimate_0241"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 241}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
