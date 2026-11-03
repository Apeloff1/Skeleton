"""Local AI Refiner launch 0361.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ID = "refiner_launch_0361"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "refiner", "local": True, "launch": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 361 % 17 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    artifacts = 1 + 361 % 5
    return {"ok": True, "id": ID, "spec": spec[:100], "artifacts": artifacts}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    score = 0.8 + (361 % 15) * 0.01
    return {"ok": True, "id": ID, "score": round(score, 3), "notes": "refined_for_launch"}
