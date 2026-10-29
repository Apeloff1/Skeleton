"""Rigid body 0005.
"""
from __future__ import annotations

BODY = "body_0005"

def mass() -> float:
    return round(1.0 + (5 % 10) * 0.5, 2)

def impulse(force: float) -> dict:
    return {"ok": True, "body": BODY, "force": force, "mass": mass()}
