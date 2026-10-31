"""Optical gate for telemetry."""
from __future__ import annotations
from typing import Dict, Any

def gate_telemetry(events: int, optical: float) -> Dict[str, Any]:
    if events < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "logged": 0}
    logged = int(events * optical)
    return {"ok": True, "logged": logged, "optical": optical, "reason": "ok"}
