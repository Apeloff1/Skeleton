"""Operational Loot 00060.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ID = "loot_ops70_00060"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "loot", "operational": True, "launch": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 60 % 19 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    return {"ok": True, "id": ID, "spec": spec[:80], "artifacts": 1 + 60 % 4}

def evaluate(outcome: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    o = outcome or {}
    score = 0.8 if o.get("success") else 0.5
    return {"ok": True, "id": ID, "score": score, "learned": bool(o.get("success"))}
