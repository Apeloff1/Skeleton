"""Bind conductor steps to optical floors."""
from __future__ import annotations
from typing import Dict, Any, List

def bind_optical(era: str, optical: float) -> Dict[str, Any]:
    if not era or optical < 0.85:
        return {"ok": False, "reason": "floors", "steps": []}
    steps = ["observe", "generate", "validate", "ratchet", "export"]
    return {"ok": True, "era": era, "steps": steps, "optical": optical, "reason": "ok"}
