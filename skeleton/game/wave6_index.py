"""Wave-6 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "scent_pack", "radio_pack", "quarantine_pack", "ration_pack", "watch_pack", "tag_pack",
    "trap_pack", "fuse_pack", "witness_pack", "badge_pack", "pass_pack", "dust_pack",
    "echo_pack", "curfew_pack", "permit_pack", "tally_pack", "cache_pack", "brand_pack",
    "vow_pack", "rift_pack", "cord_pack", "hatch_pack", "pipe_pack", "beam_pack",
    "spool_pack", "valve_pack", "latch_pack", "wick_pack", "stain_pack", "knot_pack", "pry_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave6_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
