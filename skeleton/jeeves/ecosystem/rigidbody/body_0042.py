"""Rigid body 0042.
"""
from __future__ import annotations

BODY = "body_0042"

def mass() -> float:
    return round(1.0 + (42 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
