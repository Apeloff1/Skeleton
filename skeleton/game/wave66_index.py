"""Wave-66 census."""

from __future__ import annotations

from typing import Any


PACKS = ("crib_pack", "grainbin_pack", "hayloft_pack", "weevil_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave66_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
