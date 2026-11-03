"""Local AI Builder launch 1471.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ID = "builder_launch_1471"

def describe() -> Dict[str, Any]:
    return {"id": ID, "kind": "builder", "local": True, "launch": True}

def build(spec: str = "") -> Dict[str, Any]:
    if not spec and 1471 % 17 == 0:
        return {"ok": False, "reason": "empty_spec", "id": ID}
    artifacts = 1 + 1471 % 5
    return {"ok": True, "id": ID, "spec": spec[:100], "artifacts": artifacts}

def critique(output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    score = 0.8 + (1471 % 15) * 0.01
    return {"ok": True, "id": ID, "score": round(score, 3), "notes": "refined_for_launch"}
