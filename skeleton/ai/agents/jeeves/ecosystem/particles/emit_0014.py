"""Particle emitter 0014.
"""
from __future__ import annotations

EMIT = "emit_0014"

def burst(count: int = 12) -> dict:
    count = max(1, min(64, int(count)))
    return {"ok": True, "emit": EMIT, "count": count, "lifetime": round(0.3 + (14 % 5) * 0.1, 2)}
