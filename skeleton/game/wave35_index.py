"""Wave-35 census."""

from __future__ import annotations

from typing import Any


PACKS = ("mortise_pack", "tenon_pack", "dovetail_pack", "rebate_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave35_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
