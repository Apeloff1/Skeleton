"""Counter 0039.
"""
from __future__ import annotations

COUNTER = "counter_0039"

def respond(incoming: float, timing: float) -> dict:
    success = 0.3 < timing < 0.7
    return {"ok": True, "counter": COUNTER, "success": success, "reflect": round(incoming * 0.5, 2) if success else 0.0}
