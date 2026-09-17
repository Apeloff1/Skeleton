"""Wave-96 census."""

from __future__ import annotations

from typing import Any


PACKS = ("stonewt_pack", "hundredweight_pack", "quarter_pack", "grainwt_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave96_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
