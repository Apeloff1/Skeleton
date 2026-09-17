"""Wave-59 census."""

from __future__ import annotations

from typing import Any


PACKS = ("rasphorse_pack", "clinch_pack", "hoofpick_pack", "nailset_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave59_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
