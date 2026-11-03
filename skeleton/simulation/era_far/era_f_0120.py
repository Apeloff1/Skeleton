"""Far scattered Era_F 0120.
"""
from __future__ import annotations

ID = "era_f_far2_0120"

def describe() -> dict:
    return {"id": ID, "kind": "era_f", "scattered": True, "far": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.74 + (120 % 18) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
