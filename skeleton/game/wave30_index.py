"""Wave-30 census."""

from __future__ import annotations

from typing import Any


PACKS = ("pulp_pack", "deckle_pack", "couch_pack", "felt_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave30_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
