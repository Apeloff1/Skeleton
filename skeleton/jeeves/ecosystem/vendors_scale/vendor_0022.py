"""Vendor scale 0022.
"""
from __future__ import annotations

ID = "vendor_scale_0022"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "index": 22}

def activate(context: str = "") -> dict:
    if not context and 22 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
