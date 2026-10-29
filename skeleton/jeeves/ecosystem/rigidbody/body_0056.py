"""Rigid body 0056.
"""
from __future__ import annotations

BODY = "body_0056"

def mass() -> float:
    return round(1.0 + (56 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
