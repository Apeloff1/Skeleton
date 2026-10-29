"""Bind live conductor steps."""
from __future__ import annotations
from typing import Dict, Any, List

def bind_live(era: str, mode: str) -> Dict[str, Any]:
    if not era or not mode:
        return {"ok": False, "reason": "empty", "steps": []}
    steps = ["observe", "generate", "validate", "ratchet", "export"]
    return {"ok": True, "era": era, "mode": mode, "steps": steps, "reason": "ok"}
