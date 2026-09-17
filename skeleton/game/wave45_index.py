"""Wave-45 census."""

from __future__ import annotations

from typing import Any


PACKS = ("fluke_pack", "stock_pack", "shank_pack", "ringeye_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave45_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
