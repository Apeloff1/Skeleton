"""Rigid body 0041.
"""
from __future__ import annotations

BODY = "body_0041"

def mass() -> float:
    return round(1.0 + (41 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
