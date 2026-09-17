"""Wave-108 census."""

from __future__ import annotations

from typing import Any


PACKS = ("deedbox_pack", "docket_pack", "indenture_pack", "counterpart_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave108_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
