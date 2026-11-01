"""Mount ultimate 0165.
"""
from __future__ import annotations

ID = "mount_ultimate_0165"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 165}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
