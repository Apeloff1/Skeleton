"""Mount ultimate 0196.
"""
from __future__ import annotations

ID = "mount_ultimate_0196"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 196}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
