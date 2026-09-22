"""Deterministic progression intelligence for Playables.

Turns defensive progression state into a compact coaching/telemetry projection
without coupling to a UI or database. The projection is canonical and attested
so clients can compare identical progression evidence across sessions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.progression import Medal, ProgressionState


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def inspect_progression(raw: dict[str, Any], *, known_stages: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    state = ProgressionState.migrate(raw)
    stages = tuple(dict.fromkeys(str(item) for item in known_stages if str(item)))
    medal_counts = {medal.name.lower(): 0 for medal in Medal}
    for medal in state.medals.values():
        medal_counts[medal.name.lower()] += 1

    attempted = set(state.best) | set(state.medals)
    completed = {stage for stage, medal in state.medals.items() if medal > Medal.NONE}
    known = set(stages)
    remaining = sorted(known - completed)
    unattempted = sorted(known - attempted)
    elite = sorted(stage for stage, medal in state.medals.items() if medal == Medal.ELITE)
    best = sorted(state.best.items(), key=lambda item: (item[1], item[0]))

    payload = {
        "schema_version": 1,
        "attempted_stages": len(attempted),
        "completed_stages": len(completed),
        "known_stages": len(known),
        "completion_pct": round((len(completed & known) / len(known)) * 100, 1) if known else None,
        "medal_counts": medal_counts,
        "elite_stages": elite,
        "remaining_stages": remaining,
        "unattempted_stages": unattempted,
        "best_scores": [{"stage_id": stage, "score": score} for stage, score in best[:100]],
        "ghost_coverage": len(state.ghosts),
        "total_distance": state.total_distance,
        "unlocked": sorted(state.unlocked),
    }
    payload["attestation_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


def verify_progression_projection(projection: dict[str, Any]) -> bool:
    candidate = dict(projection)
    digest = str(candidate.pop("attestation_sha256", ""))
    return bool(digest) and hashlib.sha256(_canonical(candidate)).hexdigest() == digest
