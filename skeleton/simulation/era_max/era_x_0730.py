"""Max scattered Era_X 0730.
"""
from __future__ import annotations

ID = "era_x_max2_0730"

def describe() -> dict:
    return {"id": ID, "kind": "era_x", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (730 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
