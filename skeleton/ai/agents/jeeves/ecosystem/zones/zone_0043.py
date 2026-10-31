"""Zone 0043.
"""
from __future__ import annotations

ZONE = "zone_0043"

def contains(x: float, y: float) -> bool:
    return 0 <= x <= 100 and 0 <= y <= 100

def name() -> str:
    return ZONE
