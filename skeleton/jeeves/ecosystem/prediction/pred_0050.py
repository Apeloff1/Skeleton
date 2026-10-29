"""Prediction 0050.
"""
from __future__ import annotations

PRED = "pred_0050"

def extrapolate(pos: float, vel: float, dt: float = 0.05) -> dict:
    return {"ok": True, "pred": PRED, "pos": round(pos + vel * dt, 3)}
