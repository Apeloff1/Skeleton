"""Wave-100 census."""

from __future__ import annotations

from typing import Any


PACKS = ("colophon_pack", "explicit_pack", "incipit_pack", "terminus_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave100_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
