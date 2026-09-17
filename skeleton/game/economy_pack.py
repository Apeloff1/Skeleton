"""Named barter offers. Fail-closed spend. No coin."""

from __future__ import annotations

from typing import Any


class EconomyPackError(ValueError):
    pass


OFFER: dict[str, tuple[str, int, str, int]] = {
    "scrap_for_parts": ("scrap", 2, "parts", 1),
    "parts_for_coil": ("parts", 1, "coil", 1),
    "coil_for_key": ("coil", 1, "key", 1),
    "scrap_for_bait": ("scrap", 1, "bait", 1),
    "bait_for_sleep": ("bait", 1, "sleep", 3),
    "parts_for_hp": ("parts", 1, "hp", 4),
    "scrap_for_heat": ("scrap", 1, "heat", 2),
    "coil_for_ward": ("coil", 1, "heat", -3),
    "key_for_unlock": ("key", 1, "locked", -1),
    "xp_for_skill": ("xp", 8, "skills", 1),
    "sleep_for_dream": ("sleep", 8, "slept", 1),
    "heat_for_extract": ("heat", 8, "extracted", 1),
    "alert_for_hide": ("alert", 2, "alert", -2),
    "tokens_for_verb": ("tokens", 1, "xp", 1),
    "fog_for_clear": ("los_pen", 2, "los_pen", -2),
    "floor_for_shaft": ("scrap", 2, "floor", 1),
    "mass_for_clip": ("xp", 4, "mass", 1),
    "digest_for_seal": ("coil", 1, "digest", 1),
    "handoff_for_token": ("xp", 2, "tokens", 2),
}


def apply_offer(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OFFER:
        raise EconomyPackError(name)
    src, sn, dst, dn = OFFER[name]
    nxt = dict(state)
    if int(nxt.get(src, 0)) < sn:
        raise EconomyPackError("need")
    nxt[src] = int(nxt.get(src, 0)) - sn
    nxt[dst] = int(nxt.get(dst, 0)) + dn
    nxt["stored_prose"] = 0
    return nxt
