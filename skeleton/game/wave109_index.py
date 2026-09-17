"""Wave-109 census."""

from __future__ import annotations

from typing import Any


PACKS = ("witness_pack", "tally_pack", "notary_pack", "attestation_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave109_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
