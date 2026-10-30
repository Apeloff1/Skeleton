"""Vendor scale 0066.
"""
from __future__ import annotations

ID = "vendor_scale_0066"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "index": 66}

def activate(context: str = "") -> dict:
    if not context and 66 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
