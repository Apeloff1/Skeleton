"""Wave-94 census."""

from __future__ import annotations

from typing import Any


PACKS = ("ell_pack", "yardstick_pack", "perch_pack", "furlong_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave94_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
