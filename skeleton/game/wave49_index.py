"""Wave-49 census."""

from __future__ import annotations

from typing import Any


PACKS = ("halliard_pack", "truck_pack", "hoistlen_pack", "fly_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave49_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
