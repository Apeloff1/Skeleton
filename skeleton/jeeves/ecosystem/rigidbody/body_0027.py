"""Rigid body 0027.
"""
from __future__ import annotations

BODY = "body_0027"

def mass() -> float:
    return round(1.0 + (27 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
