"""Wave-89 census."""

from __future__ import annotations

from typing import Any


PACKS = ("marketstall_pack", "pitch_pack", "stallage_pack", "cryer_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave89_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
