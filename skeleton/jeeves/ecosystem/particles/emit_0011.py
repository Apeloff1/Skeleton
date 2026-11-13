"""Particle emitter 0011.
"""
from __future__ import annotations

EMIT = "emit_0011"

def burst(count: int = 12) -> dict:
    count = max(1, min(64, int(count)))
    return {"ok": True, "emit": EMIT, "count": count, "lifetime": round(0.3 + (11 % 5) * 0.1, 2)}
