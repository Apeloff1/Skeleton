"""Wave-107 census."""

from __future__ import annotations

from typing import Any


PACKS = ("coffer_pack", "hasp_pack", "strap_pack", "casket_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave107_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
