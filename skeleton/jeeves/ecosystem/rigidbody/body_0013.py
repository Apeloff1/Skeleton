"""Rigid body 0013.
"""
from __future__ import annotations

BODY = "body_0013"

def mass() -> float:
    return round(1.0 + (13 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
