"""
ContactEngine house-copy LoRA. absorb_steps, rank, alpha, HF and Kimi aliases, dialect house.
"""
from __future__ import annotations

import math
import re

from .seam_runtime import admit, stamp

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def attach(name: str, rank: int = 8, alpha: float = 16.0) -> dict:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("adapter name is invalid")
    if isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= 64:
        raise ValueError("rank is out of range")
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, (int, float))
        or not math.isfinite(float(alpha))
        or not 0 < float(alpha) <= 64
    ):
        raise ValueError("alpha is out of range")
    return {"name": name, "rank": rank, "alpha": float(alpha), "house": "dialect"}


def process(data: dict) -> dict:
    refused = admit("lora_contact", data)
    if refused:
        return refused
    if "name" not in data:
        return stamp("lora_contact", data, {"house": "dialect", "rank": 8, "alpha": 16.0})
    try:
        card = attach(data["name"], data.get("rank", 8), data.get("alpha", 16.0))
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "card": "lora_contact"}
    return stamp("lora_contact", data, card)
