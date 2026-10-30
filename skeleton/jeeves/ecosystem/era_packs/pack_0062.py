"""Era pack 0062.
"""
from __future__ import annotations

PACK = "era_pack_0062"
GAMING = 62 % 3 == 0

def abilities() -> list[str]:
    base = ["move", "interact"]
    if GAMING:
        base += ["jump", "shoot"]
    else:
        base.append("optical_attune")
    return base

def scale() -> float:
    return 1.0 if GAMING else 1.1
