"""Wave-60 census."""

from __future__ import annotations

from typing import Any


PACKS = ("cartaxle_pack", "linchpin_pack", "reach_pack", "bolster_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave60_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
