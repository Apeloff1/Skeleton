"""Local AI Boss launch 0438.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ID = "boss_launch_0438"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "boss", "local": True, "launch": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 438 % 17 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    artifacts = 1 + 438 % 5
    return {"ok": True, "id": ID, "spec": spec[:100], "artifacts": artifacts}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    score = 0.8 + (438 % 15) * 0.01
    return {"ok": True, "id": ID, "score": round(score, 3), "notes": "refined_for_launch"}
