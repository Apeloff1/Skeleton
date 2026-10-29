"""Dodge 0030.
"""
from __future__ import annotations

DODGE = "dodge_0030"

def evade(iframes: float = 0.2) -> dict:
    return {"ok": True, "dodge": DODGE, "iframes": iframes, "invulnerable": True}
