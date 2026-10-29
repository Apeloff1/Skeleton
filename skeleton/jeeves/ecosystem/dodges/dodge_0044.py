"""Dodge 0044.
"""
from __future__ import annotations

DODGE = "dodge_0044"

def evade(iframes: float = 0.2) -> dict:
    return {"ok": True, "dodge": DODGE, "iframes": iframes, "invulnerable": True}
