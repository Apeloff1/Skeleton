"""Wave-21 census."""

from __future__ import annotations

from typing import Any


PACKS = ("mould_pack", "sprue_pack", "flux_pack", "ingot_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave21_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
