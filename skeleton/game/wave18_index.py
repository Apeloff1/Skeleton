"""Wave-18 census."""

from __future__ import annotations

from typing import Any


PACKS = ("brine_pack", "pan_pack", "rake_pack", "crystal_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave18_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
