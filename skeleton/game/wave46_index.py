"""Wave-46 census."""

from __future__ import annotations

from typing import Any


PACKS = ("coaming_pack", "hatchlid_pack", "cleatpin_pack", "scuttle_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave46_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
