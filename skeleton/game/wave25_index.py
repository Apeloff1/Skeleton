"""Wave-25 census."""

from __future__ import annotations

from typing import Any


PACKS = ("thatch_pack", "wattle_pack", "daub_pack", "lath_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave25_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
