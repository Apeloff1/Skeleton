"""Replay-certified Lantern Quay time trials and bounded scoreboards.

A course is original authored data, not executable code. A run only earns a
medal after the canonical engine proves every ordered checkpoint, delivery,
choice, and deadline. Scoreboards are reproducible but not identity-signed.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, initial_state, normalize_action, step,
    validate_source, verify_bundle,
)
from .harbor_crafting_sessions import resume_bundle

COURSE_SCHEMA = "skeleton.game.harbor.time-trial.v1"
REPORT_SCHEMA = "skeleton.game.harbor.time-trial-report.v1"
BOARD_SCHEMA = "skeleton.game.harbor.time-trial-leaderboard.v1"
MAX_CHECKPOINTS = 12
MAX_RUNS = 8
MAX_COURSE_BYTES = 32768
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 3
MAX_BOARD_BYTES = MAX_REPORT_BYTES * MAX_RUNS + 65536
COURSE_FIELDS = {"schema", "source_id", "checkpoints", "deadline", "medals", "choice"}
REPORT_FIELDS = {
    "schema", "course", "course_digest", "bundle", "source_digest",
    "visits", "status", "medal", "finish_tick", "report_digest",
}
BOARD_FIELDS = {"schema", "course_digest", "reports", "ranking", "board_digest"}


def validate_course(course: Any, source: Any) -> dict[str, Any]:
    """Reject impossible geometry, ambiguous checkpoint IDs, and bad timing."""
    world = validate_source(source)
    _keys(course, COURSE_FIELDS, "time trial course")
    if course["schema"] != COURSE_SCHEMA or course["source_id"] != world["id"]:
        raise HarborError("time trial source mismatch")
    if len(canonical(course)) > MAX_COURSE_BYTES:
        raise HarborError("time trial course exceeds byte limit")
    deadline = _integer(course["deadline"], 1, world["max_ticks"], "trial deadline")
    if course["choice"] not in ("signal", "shelter") or type(course["choice"]) is not str:
        raise HarborError("invalid trial ending")
    medals = _keys(course["medals"], {"gold", "silver", "bronze"}, "trial medals")
    gold = _integer(medals["gold"], 1, deadline, "gold time")
    silver = _integer(medals["silver"], 1, deadline, "silver time")
    bronze = _integer(medals["bronze"], 1, deadline, "bronze time")
    if not gold < silver < bronze <= deadline:
        raise HarborError("invalid trial medal thresholds")
    checkpoints = course["checkpoints"]
    if not isinstance(checkpoints, list) or not 1 <= len(checkpoints) <= MAX_CHECKPOINTS:
        raise HarborError("invalid trial checkpoints")
    names: set[str] = set()
    coordinates: set[tuple[int, int]] = set()
    last_deadline = 0
    for entry in checkpoints:
        _keys(entry, {"id", "at", "latest_tick"}, "trial checkpoint")
        name = _identifier(entry["id"], "checkpoint id")
        if name in names:
            raise HarborError("duplicate trial checkpoint id")
        names.add(name)
        at = entry["at"]
        if not isinstance(at, list) or len(at) != 2:
            raise HarborError("invalid trial coordinate")
        x = _integer(at[0], 0, len(world["map"][0]) - 1, "trial x")
        y = _integer(at[1], 0, len(world["map"]) - 1, "trial y")
        if world["map"][y][x] != "." or at == world["start"]:
            raise HarborError("trial checkpoint is blocked or starts occupied")
        if (x, y) in coordinates:
            raise HarborError("duplicate trial checkpoint location")
        coordinates.add((x, y))
        latest = _integer(entry["latest_tick"], 1, deadline, "checkpoint deadline")
        if latest < last_deadline:
            raise HarborError("trial checkpoint deadlines must be ordered")
        last_deadline = latest
    return deepcopy(course)


def time_trial_report(bundle: Any, course: Any, *, require_finish: bool = False) -> dict[str, Any]:
    """Derive checkpoints and medals from the full verified source-bound replay."""
    state = verify_bundle(bundle)
    world = validate_source(bundle["source"])
    authored = validate_course(course, world)
    current = initial_state(world)
    visits: list[dict[str, Any]] = []
    checkpoint_index = 0
    for event in bundle["events"]:
        action = normalize_action(event["action"])
        before = current
        current = step(world, current, action)
        if checkpoint_index >= len(authored["checkpoints"]):
            continue
        target = authored["checkpoints"][checkpoint_index]
        if (
            action["op"] == "move"
            and current["pos"] == target["at"]
            and current["pos"] != before["pos"]
            and current["tick"] <= target["latest_tick"]
        ):
            visits.append({
                "id": target["id"], "tick": current["tick"],
                "event_digest": event["digest"],
            })
            checkpoint_index += 1
    if current != state:
        raise HarborError("time trial replay diverged")
    finished = (
        checkpoint_index == len(authored["checkpoints"])
        and current["ending"] == (
            "beacon" if authored["choice"] == "signal" else "safe_harbor"
        )
        and current["delivered"] is True
        and current["tick"] <= authored["deadline"]
    )
    if require_finish and not finished:
        raise HarborError("time trial finish not earned")
    medal = None
    if finished:
        for level in ("gold", "silver", "bronze"):
            if current["tick"] <= authored["medals"][level]:
                medal = level
                break
    report = {
        "schema": REPORT_SCHEMA,
        "course": authored,
        "course_digest": digest(authored),
        "bundle": deepcopy(bundle),
        "source_digest": bundle["source_digest"],
        "visits": visits,
        "status": "finished" if finished else "incomplete",
        "medal": medal,
        "finish_tick": current["tick"] if finished else None,
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("time trial report exceeds byte limit")
    return report


def verify_time_trial_report(report: Any, *, require_finish: bool = False) -> dict[str, Any]:
    """Rebuild the entire course result; resealing outer hashes cannot forge medals."""
    _keys(report, REPORT_FIELDS, "time trial report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized time trial report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("time trial report digest mismatch")
    rebuilt = time_trial_report(report["bundle"], report["course"], require_finish=require_finish)
    if rebuilt != report:
        raise HarborError("time trial replay mismatch")
    return {
        "status": rebuilt["status"],
        "medal": rebuilt["medal"],
        "finish_tick": rebuilt["finish_tick"],
        "visits": deepcopy(rebuilt["visits"]),
        "terminal_digest": rebuilt["bundle"]["terminal_digest"],
    }


def resume_time_trial(
    root: Any, course: Any, actions: Any, *, expected_terminal_digest: str,
    require_finish: bool = False,
) -> dict[str, Any]:
    """Continue an existing checkpoint using the canonical CAS replay contract."""
    resumed = resume_bundle(
        root, actions, expected_terminal_digest=expected_terminal_digest,
    )
    return time_trial_report(resumed, course, require_finish=require_finish)


def time_trial_leaderboard(reports: Any) -> dict[str, Any]:
    """Rank up to eight independently replay-verified finishes without identity claims."""
    if not isinstance(reports, list) or not 1 <= len(reports) <= MAX_RUNS:
        raise HarborError("invalid time trial leaderboard count")
    if len(canonical(reports)) > MAX_BOARD_BYTES:
        raise HarborError("time trial leaderboard exceeds byte limit")
    course_digest: str | None = None
    source_digest: str | None = None
    seen: set[str] = set()
    ranking: list[dict[str, Any]] = []
    for report in reports:
        result = verify_time_trial_report(report, require_finish=True)
        if course_digest is None:
            course_digest = report["course_digest"]
            source_digest = report["source_digest"]
        if report["course_digest"] != course_digest or report["source_digest"] != source_digest:
            raise HarborError("leaderboard contains incompatible trial source")
        bundle_digest = report["bundle"]["bundle_digest"]
        if bundle_digest in seen:
            raise HarborError("duplicate leaderboard replay")
        seen.add(bundle_digest)
        waits = sum(
            event["action"]["op"] == "wait" for event in report["bundle"]["events"]
        )
        ranking.append({
            "bundle_digest": bundle_digest,
            "terminal_digest": result["terminal_digest"],
            "finish_tick": result["finish_tick"],
            "medal": result["medal"],
            "waits": waits,
        })
    ranking.sort(key=lambda entry: (
        entry["finish_tick"], entry["waits"], entry["bundle_digest"],
    ))
    for rank, entry in enumerate(ranking, 1):
        entry["rank"] = rank
    board = {
        "schema": BOARD_SCHEMA, "course_digest": course_digest,
        "reports": deepcopy(reports), "ranking": ranking,
    }
    board["board_digest"] = digest(board)
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("time trial leaderboard exceeds byte limit")
    return board


def verify_time_trial_leaderboard(board: Any) -> list[dict[str, Any]]:
    _keys(board, BOARD_FIELDS, "time trial leaderboard")
    if board["schema"] != BOARD_SCHEMA or len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("unsupported or oversized trial leaderboard")
    if board["board_digest"] != digest({
        key: value for key, value in board.items() if key != "board_digest"
    }):
        raise HarborError("time trial leaderboard digest mismatch")
    rebuilt = time_trial_leaderboard(board["reports"])
    if rebuilt != board:
        raise HarborError("time trial leaderboard replay mismatch")
    return deepcopy(rebuilt["ranking"])
