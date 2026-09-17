"""Wave-64 census."""

from __future__ import annotations

from typing import Any


PACKS = ("swipple_pack", "handstaff_pack", "flailcap_pack", "thong_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave64_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
