"""Dodge 0031.
"""
from __future__ import annotations

DODGE = "dodge_0031"

def evade(iframes: float = 0.2) -> dict:
    return {"ok": True, "dodge": DODGE, "iframes": iframes, "invulnerable": True}
