"""Wave-112 census."""

from __future__ import annotations

from typing import Any


PACKS = ("inquisition_pack", "escheat_pack", "wardship_pack", "liveryseisin_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave112_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
