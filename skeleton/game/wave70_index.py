"""Wave-70 census."""

from __future__ import annotations

from typing import Any


PACKS = ("threshfloor_pack", "barnbay_pack", "aisle_pack", "haymow_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave70_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
