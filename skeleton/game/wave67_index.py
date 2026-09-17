"""Wave-67 census."""

from __future__ import annotations

from typing import Any


PACKS = ("harrowtine_pack", "harrowframe_pack", "drawhit_pack", "dragbar_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave67_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
