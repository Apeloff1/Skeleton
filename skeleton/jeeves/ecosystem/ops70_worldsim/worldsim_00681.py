"""Operational Worldsim 00681.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ID = "worldsim_ops70_00681"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "worldsim", "operational": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 681 % 31 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    return {"ok": True, "id": ID, "spec": spec[:60], "artifacts": 1 + 681 % 3}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"ok": True, "id": ID, "score": 0.82 + (681 % 10) * 0.01, "notes": "ops_refined"}
