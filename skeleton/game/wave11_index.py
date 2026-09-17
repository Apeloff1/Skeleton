"""Wave-11 census."""

from __future__ import annotations

from typing import Any


PACKS = ("splint_pack", "suture_pack", "poultice_pack", "tonic_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave11_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
