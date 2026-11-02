"""Mount eco_peak 0247.
"""
from __future__ import annotations

ID = "mount_eco_peak_0247"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 247}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
