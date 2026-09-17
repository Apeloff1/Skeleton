"""Wave-86 census."""

from __future__ import annotations

from typing import Any


PACKS = ("milestone_pack", "fingerpost_pack", "waymark_pack", "cairn_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave86_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
