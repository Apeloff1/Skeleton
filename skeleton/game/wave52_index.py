"""Wave-52 census."""

from __future__ import annotations

from typing import Any


PACKS = ("gnomon_pack", "style_pack", "hourline_pack", "nodus_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave52_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
