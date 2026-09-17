"""Barter book. Named offers. No coin."""

from __future__ import annotations

from typing import Any


class BarterError(ValueError):
    pass


OFFERS = {
    "scrap_for_parts": ("scrap", 2, "parts", 1),
    "parts_for_key": ("parts", 1, "key", 1),
    "bait_for_scrap": ("bait", 1, "scrap", 2),
    "coil_for_parts": ("coil", 1, "parts", 2),
    "heat_for_scrap": ("heat", 4, "scrap", 1),
    "xp_for_atk": ("xp", 10, "atk", 1),
    "key_for_extract": ("key", 1, "extract_ready", 1),
}


def can(state: dict[str, Any], name: str) -> bool:
    if name not in OFFERS:
        raise BarterError(name)
    src, sn, _dst, _dn = OFFERS[name]
    return int(state.get(src, 0)) >= sn


def apply_offer(state: dict[str, Any], name: str) -> dict[str, Any]:
    if not can(state, name):
        raise BarterError(name)
    src, sn, dst, dn = OFFERS[name]
    nxt = dict(state)
    nxt[src] = int(nxt.get(src, 0)) - sn
    nxt[dst] = int(nxt.get(dst, 0)) + dn
    nxt["last_barter"] = name
    nxt["stored_prose"] = 0
    return nxt


def book() -> list[dict[str, Any]]:
    return [
        {"offer": name, "src": src, "src_n": sn, "dst": dst, "dst_n": dn, "stored_prose": 0}
        for name, (src, sn, dst, dn) in OFFERS.items()
    ]
