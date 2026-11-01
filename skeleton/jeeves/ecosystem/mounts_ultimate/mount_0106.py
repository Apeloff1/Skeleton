"""Mount ultimate 0106.
"""
from __future__ import annotations

ID = "mount_ultimate_0106"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 106}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
