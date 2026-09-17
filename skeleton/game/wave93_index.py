"""Wave-93 census."""

from __future__ import annotations

from typing import Any


PACKS = ("steelyard_pack", "poise_pack", "fulcrum_pack", "weightpan_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave93_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
