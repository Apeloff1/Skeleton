"""Wave-106 census."""

from __future__ import annotations

from typing import Any


PACKS = ("clasp_pack", "boss_pack", "cornerpiece_pack", "foredge_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave106_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
