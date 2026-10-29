"""Zone 0002.
"""
from __future__ import annotations

ZONE = "zone_0002"

def contains(x: float, y: float) -> bool:
    return 0 <= x <= 100 and 0 <= y <= 100

def name() -> str:
    return ZONE
