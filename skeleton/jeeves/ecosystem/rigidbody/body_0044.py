"""Rigid body 0044.
"""
from __future__ import annotations

BODY = "body_0044"

def mass() -> float:
    return round(1.0 + (44 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
