"""Wave-56 census."""

from __future__ import annotations

from typing import Any


PACKS = ("felloe_pack", "spokeset_pack", "nave_pack", "tyreband_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave56_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
