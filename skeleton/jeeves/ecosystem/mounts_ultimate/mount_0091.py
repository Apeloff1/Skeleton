"""Mount ultimate 0091.
"""
from __future__ import annotations

ID = "mount_ultimate_0091"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 91}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
