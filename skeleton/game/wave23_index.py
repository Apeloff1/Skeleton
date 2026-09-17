"""Wave-23 census."""

from __future__ import annotations

from typing import Any


PACKS = ("type_pack", "chase_pack", "galley_pack", "proof_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave23_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
