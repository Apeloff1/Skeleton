"""
Speculative verify and activation steer for local AI.
Accept-until-mismatch. h becomes h plus alpha u-hat. No torch required in CI.
"""
from __future__ import annotations

import math
from typing import List

from .seam_runtime import admit, stamp


class SpecDecSteer:
    def verify(self, draft: str, target: str) -> bool:
        if not isinstance(draft, str) or not isinstance(target, str):
            return False
        if not draft or not target:
            return False
        limit = min(len(draft), len(target)) // 2
        if limit == 0:
            return False
        return draft[:limit] == target[:limit]

    def steer(self, h: List[float], u_hat: List[float], alpha: float = 0.1) -> List[float]:
        if (
            not isinstance(h, list)
            or not isinstance(u_hat, list)
            or len(h) != len(u_hat)
            or not 1 <= len(h) <= 64
        ):
            raise ValueError("steer vectors must match and stay within 64")
        if (
            isinstance(alpha, bool)
            or not isinstance(alpha, (int, float))
            or not math.isfinite(float(alpha))
            or not 0 < float(alpha) <= 1
        ):
            raise ValueError("alpha is out of range")
        steered: list[float] = []
        for height, update in zip(h, u_hat):
            if (
                isinstance(height, bool)
                or isinstance(update, bool)
                or not isinstance(height, (int, float))
                or not isinstance(update, (int, float))
                or not math.isfinite(float(height))
                or not math.isfinite(float(update))
            ):
                raise ValueError("steer vectors must be numbers")
            steered.append(float(height) + float(alpha) * float(update))
        return steered


def process(data: dict) -> dict:
    refused = admit("specdec_steer", data)
    if refused:
        return refused
    if "h" not in data and "u" not in data:
        return stamp("specdec_steer", data, {"alpha": 0.1})
    try:
        steered = SpecDecSteer().steer(data.get("h"), data.get("u"), data.get("alpha", 0.1))
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "card": "specdec_steer"}
    alpha = data.get("alpha", 0.1)
    return stamp("specdec_steer", data, {"alpha": float(alpha), "steered": steered})
