"""Local AI Critic launch 0516.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ID = "critic_launch_0516"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "critic", "local": True, "launch": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 516 % 17 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    artifacts = 1 + 516 % 5
    return {"ok": True, "id": ID, "spec": spec[:100], "artifacts": artifacts}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    score = 0.8 + (516 % 15) * 0.01
    return {"ok": True, "id": ID, "score": round(score, 3), "notes": "refined_for_launch"}
