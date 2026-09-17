"""Wave-88 census."""

from __future__ import annotations

from typing import Any


PACKS = ("taproom_pack", "cellar_pack", "innsign_pack", "settle_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave88_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
