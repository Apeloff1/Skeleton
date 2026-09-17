"""Wave-43 census."""

from __future__ import annotations

from typing import Any


PACKS = ("oakum_pack", "pitchlot_pack", "seam_pack", "caulkiron_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave43_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
