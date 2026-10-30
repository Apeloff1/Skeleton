"""Buff mega 0026.
"""
from __future__ import annotations

ID = "buff_mega_0026"

def describe() -> dict:
    return {"id": ID, "kind": "buff", "power": 5 + (26 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
