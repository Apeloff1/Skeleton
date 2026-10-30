"""Era pack 0122.
"""
from __future__ import annotations

PACK = "era_pack_0122"
GAMING = 122 % 3 == 0

def abilities() -> list[str]:
    base = ["move", "interact"]
    if GAMING:
        base += ["jump", "shoot"]
    else:
        base.append("optical_attune")
    return base

def scale() -> float:
    return 1.0 if GAMING else 1.1
