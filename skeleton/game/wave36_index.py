"""Wave-36 census."""

from __future__ import annotations

from typing import Any


PACKS = ("hardy_pack", "fuller_pack", "swage_pack", "drift_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave36_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
