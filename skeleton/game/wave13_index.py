"""Wave-13 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "hive_pack", "comb_pack", "swarm_pack", "smoke_pack",
    "queen_pack", "frame_pack", "honey_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave13_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
