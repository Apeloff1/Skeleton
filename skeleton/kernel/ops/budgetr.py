"""R budget from hardware profile.

tight=1 mobile=2 desktop=3 max=4. Never above cap even if ponder wants more.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops._stat import bump

CAP = {"tight": 1, "mobile": 2, "desktop": 3, "workstation": 4, "max": 4}


def cap(profile: str = "mobile") -> int:
    return int(CAP.get(str(profile or "mobile"), 2))


def budget(*, profile: str = "mobile", want: int = 2, halt: bool = False) -> Dict[str, Any]:
    c = cap(profile)
    r = max(1, min(c, int(want)))
    if not halt and r > 2:
        r = 2
    bump(1)
    return {
        "kind": "r-budget",
        "profile": profile,
        "cap": c,
        "r": r,
        "stored_prose": 0,
    }
