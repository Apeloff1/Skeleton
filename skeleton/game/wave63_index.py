"""Wave-63 census."""

from __future__ import annotations

from typing import Any


PACKS = ("snath_pack", "tang_pack", "scytheheel_pack", "beard_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave63_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
