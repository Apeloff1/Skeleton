"""Rigid body 0053.
"""
from __future__ import annotations

BODY = "body_0053"

def mass() -> float:
    return round(1.0 + (53 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
