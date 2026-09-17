"""Wave-101 census."""

from __future__ import annotations

from typing import Any


PACKS = ("quire_pack", "rubric_pack", "catchword_pack", "pricking_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave101_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
