"""Wave-33 census."""

from __future__ import annotations

from typing import Any


PACKS = ("scratch_pack", "brown_pack", "skim_pack", "float_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave33_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
