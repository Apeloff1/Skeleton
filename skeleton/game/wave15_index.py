"""Wave-15 census."""

from __future__ import annotations

from typing import Any


PACKS = ("loom_pack", "warp_pack", "weft_pack", "shuttle_pack", "heddle_pack", "reed_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave15_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
