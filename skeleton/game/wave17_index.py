"""Wave-17 census."""

from __future__ import annotations

from typing import Any


PACKS = ("hide_pack", "vat_pack", "lime_pack", "bark_pack", "hoop_pack", "stave_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave17_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
