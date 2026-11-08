"""Model promotion gate: shadow -> canary -> production, each stage with a
receipt; production requires a tested rollback."""
from __future__ import annotations

from ._stats import require

NAME = "promotion"
PARAMS = {"max_canary_regression": float}
ORDER = ("shadow", "canary", "production")


def evaluate(params: dict, data: dict) -> tuple[list[str], dict]:
    missing = require(data, "stages")
    if missing:
        return missing, {}
    stages = data["stages"]
    if (type(stages) is not list or not 1 <= len(stages) <= len(ORDER)
            or any(type(s) is not dict or type(s.get("stage")) is not str
                   or type(s.get("receipt")) is not str for s in stages)):
        return ["invalid or empty bounded promotion stage evidence"], {}
    names = [s.get("stage") for s in stages]
    reasons: list[str] = []
    if names != list(ORDER[: len(names)]):
        reasons.append(f"stages out of order: {names}")
    for s in stages:
        if not s.get("receipt"):
            reasons.append(f"stage '{s.get('stage')}' has no release receipt")
    canary = next((s for s in stages if s.get("stage") == "canary"), None)
    if canary and canary.get("regression", 0) > params["max_canary_regression"]:
        reasons.append(f"canary regression {canary['regression']:g} > {params['max_canary_regression']:g}")
    if "production" in names and not data.get("rollback_tested"):
        reasons.append("production promotion without a tested rollback")
    return reasons, {"stages": names}
