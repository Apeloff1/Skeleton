"""Wave-79 census."""

from __future__ import annotations

from typing import Any


PACKS = ("weir_pack", "fyke_pack", "creel_pack", "longline_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave79_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
