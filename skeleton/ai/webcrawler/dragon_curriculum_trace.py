"""Finite pre-dispatch curriculum receipts and settlement analysis.

A receipt describes why an already-eligible frontier entry took priority.
It is attached to the canonical request reservation before transport, then
settled with that reservation's actual outcome. No raw URL or source text
is stored in the receipt. It cannot authorize a fetch.
"""
from __future__ import annotations

import hashlib
import math
import re

_MODES = {"companion", "companion_curiosity", "companion_scholar", "companion_guardian"}
_QUESTS = {"explore", "synthesize", "diversify", "conserve", "recover", "rest"}
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_FIELDS = {"strategy", "quest", "candidate_digest", "eligible", "base_milli",
           "priority_milli", "phase", "network_authority_expanded"}


def _digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def decision_receipt(*, mode: str, quest: str, candidate: str,
                     eligible: int, base: float, priority: float, policy: bool) -> dict:
    if (not isinstance(candidate, str) or not 1 <= len(candidate.encode("utf-8")) <= 4096
            or type(policy) is not bool):
        raise ValueError("invalid curriculum candidate")
    if any(isinstance(x, bool) or not isinstance(x, (int, float))
           or not math.isfinite(x) or not 0 <= x <= 1 for x in (base, priority)):
        raise ValueError("invalid curriculum scores")
    row = {"strategy": mode, "quest": quest, "candidate_digest": _digest(candidate),
           "eligible": eligible, "base_milli": round(base*1000),
           "priority_milli": round(priority*1000),
           "phase": "policy" if policy else "content", "network_authority_expanded": False}
    validate_receipt(row, mode=mode, candidate=candidate)
    return row


def validate_receipt(value: object, *, mode: str | None = None,
                     candidate: str | None = None) -> None:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError("invalid curriculum receipt schema")
    if (value["strategy"] not in _MODES or (mode is not None and value["strategy"] != mode)
            or value["quest"] not in _QUESTS or value["phase"] not in {"policy", "content"}
            or value["network_authority_expanded"] is not False
            or not isinstance(value["candidate_digest"], str)
            or not _HEX.fullmatch(value["candidate_digest"])
            or candidate is not None and value["candidate_digest"] != _digest(candidate)
            or type(value["eligible"]) is not int or not 1 <= value["eligible"] <= 512):
        raise ValueError("invalid curriculum receipt binding")
    for key in ("base_milli", "priority_milli"):
        if type(value[key]) is not int or not 0 <= value[key] <= 1000:
            raise ValueError("invalid curriculum score")
    delta = abs(value["priority_milli"] - value["base_milli"])
    if delta > 121 or value["quest"] in {"rest", "recover", "conserve"} and delta:
        raise ValueError("curriculum influence exceeded its permitted envelope")


def trace_summary(measurements: list[dict]) -> dict:
    if not isinstance(measurements, list) or len(measurements) > 128:
        raise ValueError("invalid curriculum trace capacity")
    traces = []
    summary = {key: {"content_attempts": 0, "captures": 0, "policy_attempts": 0,
                     "uncertain_attempts": 0} for key in sorted(_QUESTS)}
    for row in measurements:
        trace = row.get("curriculum")
        if trace is None:
            continue
        validate_receipt(trace)
        counts = summary[trace["quest"]]
        counts["policy_attempts" if trace["phase"] == "policy" else "content_attempts"] += 1
        counts["captures"] += int(trace["phase"] == "content" and row["kind"] == "captured")
        counts["uncertain_attempts"] += int(row["status"] is None)
        traces.append({**trace, "request": row["request"], "event_sequence": row["event_sequence"],
                       "outcome": row["kind"], "source_id": row.get("source_id")})
    return {"decisions": len(traces), "quests": summary, "recent": traces[-8:],
            "training_permission": False, "network_authority_expanded": False}
