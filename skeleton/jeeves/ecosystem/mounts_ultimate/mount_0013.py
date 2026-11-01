"""Mount ultimate 0013.
"""
from __future__ import annotations

ID = "mount_ultimate_0013"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 13}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
