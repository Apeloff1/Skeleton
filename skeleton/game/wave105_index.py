"""Wave-105 census."""

from __future__ import annotations

from typing import Any


PACKS = ("goldleaf_pack", "burnish_pack", "tooling_pack", "fillet_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave105_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
