"""Wave-32 census."""

from __future__ import annotations

from typing import Any


PACKS = ("slake_pack", "putty_pack", "mortar_pack", "hair_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave32_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
