"""Spy op 0000.
"""
from __future__ import annotations

SPY = "spy_0000"

def infiltrate(target: str, skill: float = 0.5) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": skill > 0.4, "spy": SPY, "target": target, "intel": skill > 0.6}
