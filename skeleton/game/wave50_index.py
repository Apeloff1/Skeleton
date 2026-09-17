"""Wave-50 census."""

from __future__ import annotations

from typing import Any


PACKS = ("bung_pack", "croze_pack", "adze_pack", "chime_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave50_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
