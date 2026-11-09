"""Validator gate 00.
"""
from __future__ import annotations

GATE = "gate_00"
FLOOR = round(0.85 + (0 % 5) * 0.02, 2)

def check(value: float) -> dict:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return {"ok": False, "gate": GATE, "reason": "not_numeric"}
    return {"ok": v >= FLOOR, "gate": GATE, "value": v, "floor": FLOOR}
