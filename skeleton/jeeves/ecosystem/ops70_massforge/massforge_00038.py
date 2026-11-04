"""Operational Massforge 00038.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ID = "massforge_ops70_00038"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "massforge", "operational": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 38 % 31 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    return {"ok": True, "id": ID, "spec": spec[:60], "artifacts": 1 + 38 % 3}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"ok": True, "id": ID, "score": 0.82 + (38 % 10) * 0.01, "notes": "ops_refined"}
