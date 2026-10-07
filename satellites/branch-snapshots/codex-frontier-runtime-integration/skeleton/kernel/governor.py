"""Mid-run kernel governor. Pressure flips the live profile.

tighten at 0.82 → force tight. Ease only after two probes ≤ 0.55.
Env SKELETON_KERNEL still wins over auto, loses to force() only
when the governor is ticking (force is the runtime latch).
"""
from __future__ import annotations

from typing import Any, Dict

TIGHT = 0.82
CALM = 0.55

_CALM = 0
_LAST = ""


def tick(pressure: float | None = None) -> Dict[str, Any]:
    global _CALM, _LAST
    from skeleton.kernel.profiles import card, force, pick

    if pressure is None:
        try:
            from skeleton.organism.caps import live
            pressure = float(live().pressure)
        except Exception:
            pressure = 0.0
    pressure = float(pressure)
    now = card()
    name = str(now.get("profile") or pick(pressure=pressure))
    action = "hold"
    if pressure >= TIGHT:
        force("tight")
        action = "tighten" if _LAST != "tight" else "hold"
        _CALM = 0
        _LAST = "tight"
    elif pressure <= CALM and _LAST == "tight":
        _CALM += 1
        if _CALM >= 2:
            force("")
            action = "ease"
            _CALM = 0
            _LAST = ""
        else:
            action = "hold"
    else:
        if pressure > CALM:
            _CALM = 0
    after = card()
    rebuilt = 0
    if action in {"tighten", "ease"}:
        try:
            from skeleton.kernel.switch import to as switch_to
            target = "tight" if action == "tighten" else str(after.get("profile") or pick(pressure=pressure))
            switch_to(target)
            rebuilt = 1
        except Exception:
            rebuilt = 0
    out = {
        "kind": "kernel-gov",
        "action": action,
        "pressure": round(pressure, 4),
        "profile": after.get("profile"),
        "was": name,
        "rebuilt": rebuilt,
        "stored_prose": 0,
    }
    try:
        from skeleton.kernel.persist import save_gov
        save_gov(out)
    except Exception:
        pass
    return out
