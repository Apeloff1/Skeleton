"""Operational Worldsim 00393.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ID = "worldsim_ops70_00393"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "worldsim", "operational": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 393 % 31 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    return {"ok": True, "id": ID, "spec": spec[:60], "artifacts": 1 + 393 % 3}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"ok": True, "id": ID, "score": 0.82 + (393 % 10) * 0.01, "notes": "ops_refined"}
