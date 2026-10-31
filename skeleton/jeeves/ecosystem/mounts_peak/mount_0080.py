"""Mount peak 0080.
"""
from __future__ import annotations

ID = "mount_peak_0080"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 80}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
