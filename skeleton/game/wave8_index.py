"""Wave-8 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "bellows_pack", "anvil_pack", "quench_pack", "slag_pack", "bloom_pack", "tongs_pack",
    "temper_pack", "scale_pack", "grind_pack", "kiln_pack", "glaze_pack", "shard_pack",
    "mold_pack", "hopper_pack", "chute_pack", "sieve_pack", "mill_pack", "millstone_pack",
    "ingot_pack", "billet_pack", "crucible_pack", "tuyere_pack", "flux_pack", "char_pack",
    "ore_pack", "workorder_pack", "lot_pack", "batch_pack", "smith_pack", "hearth_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave8_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
