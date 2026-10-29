"""Rigid body 0010.
"""
from __future__ import annotations

BODY = "body_0010"

def mass() -> float:
    return round(1.0 + (10 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
