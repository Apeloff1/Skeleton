"""Teleport eco_peak 0272.
"""
from __future__ import annotations

ID = "teleport_eco_peak_0272"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "teleport"}
