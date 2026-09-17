"""Wave-97 census."""

from __future__ import annotations

from typing import Any


PACKS = ("statute_pack", "charter_pack", "roll_pack", "letters_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave97_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
