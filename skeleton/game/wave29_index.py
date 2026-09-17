"""Wave-29 census."""

from __future__ import annotations

from typing import Any


PACKS = ("wick_pack", "dip_pack", "snuff_pack", "taper_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave29_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
