"""Wave-44 census."""

from __future__ import annotations

from typing import Any


PACKS = ("capstan_pack", "windlass_pack", "pawl_pack", "barrel_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave44_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
