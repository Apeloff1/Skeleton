"""Max scattered Auto_X 0120.
"""
from __future__ import annotations

ID = "auto_x_max2_0120"

def describe() -> dict:
    return {"id": ID, "kind": "auto_x", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (120 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
