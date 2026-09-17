"""Wave-74 census."""

from __future__ import annotations

from typing import Any


PACKS = ("maltfloor_pack", "maltsteep_pack", "kilnmalt_pack", "grist_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave74_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
