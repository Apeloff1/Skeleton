"""Wave-5 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "noise_map", "faction_pack", "clock_pack", "vendor_pack", "wound_pack", "light_pack",
    "temp_pack", "mark_pack", "ammo_pack", "rumor_pack", "cargo_pack", "contract_pack",
    "flag_pack", "lease_pack", "rep_pack", "tool_pack", "ward_pack", "lure_pack",
    "mood_pack", "diet_pack", "bond_pack", "note_pack", "shift_pack", "courier_pack",
    "toll_pack", "oath_pack", "veil_pack", "pulse_pack", "gate_pack", "choir_pack",
    "rink_pack", "event_pack", "kin_pack", "bin_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave5_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
