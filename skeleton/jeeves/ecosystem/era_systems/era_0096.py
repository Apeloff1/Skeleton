"""Era system 0096.
"""
from __future__ import annotations

ERA = "era_sys_0096"

def swap(from_era: str, to_era: str) -> dict:
    if not from_era or not to_era:
        return {"ok": False, "reason": "missing"}
    return {"ok": True, "era": ERA, "from": from_era, "to": to_era, "scale": 1.0 if to_era in ("NES","SNES") else 1.1}
