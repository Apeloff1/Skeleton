"""Vendor scale 0038.
"""
from __future__ import annotations

ID = "vendor_scale_0038"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "index": 38}

def activate(context: str = "") -> dict:
    if not context and 38 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
