"""Wave-75 census."""

from __future__ import annotations

from typing import Any


PACKS = ("wormcoil_pack", "retort_pack", "wash_pack", "foreshot_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave75_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
