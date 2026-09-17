"""Wave-53 census."""

from __future__ import annotations

from typing import Any


PACKS = ("arming_pack", "soundmark_pack", "handlead_pack", "deepsea_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave53_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
