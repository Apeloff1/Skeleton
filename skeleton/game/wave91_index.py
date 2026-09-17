"""Wave-91 census."""

from __future__ import annotations

from typing import Any


PACKS = ("assay_pack", "touchstone_pack", "hallmark_pack", "carat_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave91_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
