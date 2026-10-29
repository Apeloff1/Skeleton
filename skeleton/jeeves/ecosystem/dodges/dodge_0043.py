"""Dodge 0043.
"""
from __future__ import annotations

DODGE = "dodge_0043"

def evade(iframes: float = 0.2) -> dict:
    return {"ok": True, "dodge": DODGE, "iframes": iframes, "invulnerable": True}
