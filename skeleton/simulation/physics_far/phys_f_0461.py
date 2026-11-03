"""Far scattered Phys_F 0461.
"""
from __future__ import annotations

ID = "phys_f_far2_0461"

def describe() -> dict:
    return {"id": ID, "kind": "phys_f", "scattered": True, "far": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.74 + (461 % 18) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
