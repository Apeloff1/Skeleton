"""Door eco_prime 0300.
"""
from __future__ import annotations

ID = "door_eco_prime_0300"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "door"}
