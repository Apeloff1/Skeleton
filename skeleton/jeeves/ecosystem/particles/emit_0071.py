"""Particle emitter 0071.
"""
from __future__ import annotations

EMIT = "emit_0071"

def burst(count: int = 12) -> dict:
    count = max(1, min(64, int(count)))
    return {"ok": True, "emit": EMIT, "count": count, "lifetime": round(0.3 + (71 % 5) * 0.1, 2)}
