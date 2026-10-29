"""Particle emitter 0022.
"""
from __future__ import annotations

EMIT = "emit_0022"

def burst(count: int = 12) -> dict:
    count = max(1, min(64, int(count)))
    return {"ok": True, "emit": EMIT, "count": count, "lifetime": round(0.3 + (22 % 5) * 0.1, 2)}
