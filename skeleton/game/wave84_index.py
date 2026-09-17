"""Wave-84 census."""

from __future__ import annotations

from typing import Any


PACKS = ("throughstone_pack", "cope_pack", "batter_pack", "footing_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave84_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
