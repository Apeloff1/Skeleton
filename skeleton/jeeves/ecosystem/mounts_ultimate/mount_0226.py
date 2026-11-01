"""Mount ultimate 0226.
"""
from __future__ import annotations

ID = "mount_ultimate_0226"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 226}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
