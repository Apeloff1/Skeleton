"""Validator gate 14.
"""
from __future__ import annotations

GATE = "gate_14"
FLOOR = round(0.85 + (14 % 5) * 0.02, 2)

def check(value: float) -> dict:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return {"ok": False, "gate": GATE, "reason": "not_numeric"}
    return {"ok": v >= FLOOR, "gate": GATE, "value": v, "floor": FLOOR}
