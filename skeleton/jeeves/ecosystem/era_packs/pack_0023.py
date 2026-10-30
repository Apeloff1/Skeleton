"""Era pack 0023.
"""
from __future__ import annotations

PACK = "era_pack_0023"
GAMING = 23 % 3 == 0

def abilities() -> list[str]:
    base = ["move", "interact"]
    if GAMING:
        base += ["jump", "shoot"]
    else:
        base.append("optical_attune")
    return base

def scale() -> float:
    return 1.0 if GAMING else 1.1
