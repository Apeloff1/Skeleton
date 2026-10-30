"""Vendor scale 0064.
"""
from __future__ import annotations

ID = "vendor_scale_0064"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "index": 64}

def activate(context: str = "") -> dict:
    if not context and 64 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
