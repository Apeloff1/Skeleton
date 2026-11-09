"""Validator gate 02.
"""
from __future__ import annotations

GATE = "gate_02"
FLOOR = round(0.85 + (2 % 5) * 0.02, 2)

def check(value: float) -> dict:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return {"ok": False, "gate": GATE, "reason": "not_numeric"}
    return {"ok": v >= FLOOR, "gate": GATE, "value": v, "floor": FLOOR}
