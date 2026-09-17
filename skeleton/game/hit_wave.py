"""Wave-4 combat hits."""

from __future__ import annotations

from typing import Any


class HitWaveError(ValueError):
    pass


HIT = {f"hit_{i:02d}": (1 + (i % 5), (i % 3) - 1, 1 + (i % 2)) for i in range(20)}


def strike(name: str, state: dict[str, Any], foe: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if name not in HIT:
        raise HitWaveError(name)
    dmg, alert, cost = HIT[name]
    s, f = dict(state), dict(foe)
    if int(s.get("tokens", 8)) < cost:
        raise HitWaveError("tokens")
    f["hp"] = max(0, int(f.get("hp", 20)) - dmg)
    s["alert"] = max(0, int(s.get("alert", 0)) + alert)
    s["tokens"] = max(0, int(s.get("tokens", 8)) - cost)
    s["stored_prose"] = 0
    f["stored_prose"] = 0
    return s, f
