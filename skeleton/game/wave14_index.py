"""Wave-14 census."""

from __future__ import annotations

from typing import Any


PACKS = ("glass_pack", "bench_pack", "mist_pack", "pot_pack", "shade_pack", "soil_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave14_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
