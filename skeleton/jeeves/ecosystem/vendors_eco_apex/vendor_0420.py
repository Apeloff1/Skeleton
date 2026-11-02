"""Vendor eco_apex 0420.
"""
from __future__ import annotations

ID = "vendor_eco_apex_0420"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "vendor"}
