"""
Emit DNAHelix pairs on forge and read them from the genos organ. Persist helix file under chronicle.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

PAIRS: list[dict] = []
_CAP = 32
_LIMIT = 200


def emit(pair: dict) -> None:
    if not isinstance(pair, dict) or set(pair) != {"left", "right"}:
        raise ValueError("helix pair must have left and right")
    left = pair["left"]
    right = pair["right"]
    if not isinstance(left, str) or not isinstance(right, str):
        raise ValueError("helix pair must have left and right")
    if not left or not right or len(left) > _LIMIT or len(right) > _LIMIT:
        raise ValueError("helix pair must have left and right")
    if any(ord(ch) < 32 for ch in left + right):
        raise ValueError("helix pair must have left and right")
    stored = {"left": left, "right": right}
    if stored in PAIRS:
        return
    if len(PAIRS) >= _CAP:
        raise ValueError("helix is full")
    PAIRS.append(stored)


def process(data: dict) -> dict:
    refused = admit("dna_genos", data)
    if refused:
        return refused
    if "left" not in data and "right" not in data:
        return stamp("dna_genos", data, {"pairs": len(PAIRS)})
    try:
        emit({"left": data.get("left"), "right": data.get("right")})
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "card": "dna_genos"}
    return stamp("dna_genos", data, {"pairs": len(PAIRS)})
