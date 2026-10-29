"""Dodge 0054.
"""
from __future__ import annotations

DODGE = "dodge_0054"

def evade(iframes: float = 0.2) -> dict:
    return {"ok": True, "dodge": DODGE, "iframes": iframes, "invulnerable": True}
