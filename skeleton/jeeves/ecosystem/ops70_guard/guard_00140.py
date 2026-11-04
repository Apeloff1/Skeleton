"""Operational Guard 00140.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ID = "guard_ops70_00140"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "guard", "operational": True, "deep": True}

def operate(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = payload or {}
    if not p and 140 % 29 == 0:
        return {"ok": False, "reason": "empty_payload", "id": ID}
    return {"ok": True, "id": ID, "result": "ops", "size": len(p)}

def validate() -> Dict[str, Any]:
    return {"ok": True, "id": ID, "valid": True, "score": 0.86 + (140 % 8) * 0.01}
