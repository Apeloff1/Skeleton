"""Era pack: PS1.
"""
from __future__ import annotations

ERA = "PS1"
GAMING = ERA in ("NES", "SNES", "GB", "GBC", "GBA", "N64", "PS1", "PS2", "Dreamcast", "Arcade")

def abilities() -> list[str]:
    base = ["move", "interact", "salvage"]
    if GAMING:
        base += ["jump", "shoot"]
    else:
        base.append("optical_attune")
    return base

def scale() -> float:
    return 1.0 if GAMING else 1.1

def palette() -> list[str]:
    if GAMING:
        return ["#1a1a2e", "#e94560", "#0f3460"]
    return ["#0d0d0d", "#a78bfa", "#fbbf24"]
