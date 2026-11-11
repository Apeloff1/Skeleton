"""Long-run soak gate: duration, memory growth slope, error rate, restarts."""
from __future__ import annotations

import math
from ._stats import linear_slope
from ._stats import require

NAME = "soak"
PARAMS = {"min_hours": float, "max_rss_mb_per_hour": float, "max_error_rate": float, "max_restarts": int}


def evaluate(params: dict, data: dict) -> tuple[list[str], dict]:
    missing = require(data, "hours", "rss_mb", "requests", "errors", "restarts")
    if missing:
        return missing, {}
    if (type(data["hours"]) not in (int, float) or not math.isfinite(data["hours"])
            or data["hours"] <= 0 or type(data["rss_mb"]) is not list
            or len(data["rss_mb"]) > 100000
            or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0
                   for x in data["rss_mb"])
            or any(type(data[x]) is not int or data[x] < 0
                   for x in ("requests", "errors", "restarts"))
            or data["errors"] > data["requests"]):
        return ["invalid bounded soak measurement"], {}
    reasons: list[str] = []
    hours = float(data["hours"])
    rss = data["rss_mb"]
    slope = linear_slope(rss, [hours * i / max(1, len(rss) - 1) for i in range(len(rss))])
    err_rate = data["errors"] / data["requests"] if data["requests"] else 1.0
    metrics = {"hours": hours, "rss_slope_mb_h": round(slope, 4), "error_rate": err_rate,
               "restarts": data["restarts"]}
    if hours < params["min_hours"]:
        reasons.append(f"soak ran {hours:g} h, need {params['min_hours']:g} h")
    if len(rss) < 3:
        reasons.append("need at least 3 rss samples to judge growth")
    elif slope > params["max_rss_mb_per_hour"]:
        reasons.append(f"memory grows {slope:.2f} MB/h > {params['max_rss_mb_per_hour']:g}")
    if err_rate > params["max_error_rate"]:
        reasons.append(f"error rate {err_rate:.4%} > {params['max_error_rate']:.4%}")
    if data["restarts"] > params["max_restarts"]:
        reasons.append(f"{data['restarts']} restarts > {params['max_restarts']}")
    return reasons, metrics
