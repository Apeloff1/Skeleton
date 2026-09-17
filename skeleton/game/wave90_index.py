"""Wave-90 census."""

from __future__ import annotations

from typing import Any


PACKS = ("guildhall_pack", "guildmark_pack", "apprentice_pack", "journeyman_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave90_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
