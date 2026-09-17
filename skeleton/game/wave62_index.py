"""Wave-62 census."""

from __future__ import annotations

from typing import Any


PACKS = ("ploughshare_pack", "coulter_pack", "ploughbeam_pack", "mouldboard_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave62_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
