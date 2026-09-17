"""Wave-26 census."""

from __future__ import annotations

from typing import Any


PACKS = ("gather_pack", "blowpipe_pack", "marver_pack", "pontil_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave26_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
