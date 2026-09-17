"""Wave-31 census."""

from __future__ import annotations

from typing import Any


PACKS = ("pug_pack", "clamp_pack", "frog_pack", "batch_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave31_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
