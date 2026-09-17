"""Wave-27 census."""

from __future__ import annotations

from typing import Any


PACKS = ("mordant_pack", "indigo_pack", "madder_pack", "bath_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave27_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
