"""Operational Level 01464.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ID = "level_ops70_01464"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "level", "operational": True, "launch": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 1464 % 19 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    return {"ok": True, "id": ID, "spec": spec[:80], "artifacts": 1 + 1464 % 4}

def evaluate(outcome: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    o = outcome or {}
    score = 0.8 if o.get("success") else 0.5
    return {"ok": True, "id": ID, "score": score, "learned": bool(o.get("success"))}
