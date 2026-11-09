"""Zone 0037.
"""
from __future__ import annotations

ZONE = "zone_0037"

def contains(x: float, y: float) -> bool:
    return 0 <= x <= 100 and 0 <= y <= 100

def name() -> str:
    return ZONE
