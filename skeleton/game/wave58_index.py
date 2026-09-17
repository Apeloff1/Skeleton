"""Wave-58 census."""

from __future__ import annotations

from typing import Any


PACKS = ("hame_pack", "traceset_pack", "horsecollar_pack", "breeching_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave58_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
