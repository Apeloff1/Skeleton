"""Compose S, Sigma, Omega, smash, heart, thin bus."""

from __future__ import annotations

from typing import Any

from skeleton.motive.bus import spine_bus_card
from skeleton.motive.cards import motive_card
from skeleton.motive.heart import heart, heart_card
from skeleton.motive.ops import map_s_s_is_s, omega_sigma_iso_id, smash, suspend
from skeleton.motive.space import sphere


class MotiveEngine:
    def snapshot(self) -> dict[str, Any]:
        s = sphere()
        iso = omega_sigma_iso_id(s)
        maps = map_s_s_is_s()
        h = heart(s)
        bus = spine_bus_card()
        hc = heart_card()
        ok = iso and maps and h == 1 and bus["hit"] == 1 and hc["hit"] == 1
        sm = smash(s, s)
        sus = suspend(s)
        return motive_card(
            kind="motive",
            hit=1 if ok else 0,
            law="motive 1.0",
            extra={
                "H0": h,
                "iso": int(iso),
                "map_ss": int(maps),
                "smash": sm.name,
                "sigma": sus.name,
                "bus": bus.get("bus"),
            },
        )
