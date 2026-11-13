"""Replay-verified, source-bound multi-round Lantern Quay championship.

Season progress is an immutable portable save. Each earned result is recomputed
from the canonical movement/crafting/choice event chain; digest fields are
integrity checks, not authentication or player identity.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, validate_source, verify_bundle,
)
from .harbor_crafting_time_trials import time_trial_report, validate_course

SEASON_SCHEMA = "skeleton.game.harbor.season.v1"
RECORD_SCHEMA = "skeleton.game.harbor.season-record.v1"
BOARD_SCHEMA = "skeleton.game.harbor.season-board.v1"
MAX_ROUNDS = 8
MAX_ENTRANTS = 8
MAX_SEASON_BYTES = 262144
MAX_RECORD_BYTES = MAX_BUNDLE_BYTES * MAX_ROUNDS * 3 + MAX_SEASON_BYTES
MAX_BOARD_BYTES = MAX_RECORD_BYTES * MAX_ENTRANTS + 65536
SEASON_FIELDS = {"schema", "source_id", "rounds", "points"}
RECORD_FIELDS = {
    "schema", "source", "source_digest", "season", "season_digest",
    "results", "next_round", "total_points", "complete", "record_digest",
}
BOARD_FIELDS = {"schema", "source_digest", "season_digest", "records", "ranking", "board_digest"}


def validate_season(value: Any, source: Any) -> dict[str, Any]:
    """Require a bounded, ordered and uniquely identified authored championship."""
    world = validate_source(source)
    _keys(value, SEASON_FIELDS, "season")
    if value["schema"] != SEASON_SCHEMA or value["source_id"] != world["id"]:
        raise HarborError("season source mismatch")
    if len(canonical(value)) > MAX_SEASON_BYTES:
        raise HarborError("season exceeds byte limit")
    rounds = value["rounds"]
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= MAX_ROUNDS:
        raise HarborError("invalid season round count")
    points = _keys(value["points"], {"gold", "silver", "bronze", "finish"}, "season points")
    scores = [_integer(points[k], 1, 100, "season points") for k in ("gold", "silver", "bronze", "finish")]
    if not scores[0] > scores[1] > scores[2] > scores[3]:
        raise HarborError("season points must be strictly descending")
    ids: set[str] = set()
    course_digests: set[str] = set()
    for round_spec in rounds:
        _keys(round_spec, {"id", "course"}, "season round")
        name = _identifier(round_spec["id"], "season round id")
        if name in ids:
            raise HarborError("duplicate season round id")
        ids.add(name)
        course = validate_course(round_spec["course"], world)
        course_digest = digest(course)
        if course_digest in course_digests:
            raise HarborError("duplicate season course")
        course_digests.add(course_digest)
    return deepcopy(value)


def build_season(source: Any, season: Any, bundles: Any) -> dict[str, Any]:
    """Rebuild the full earned season from the original source and verified runs."""
    world = validate_source(source)
    authored = validate_season(season, world)
    if not isinstance(bundles, list) or len(bundles) > len(authored["rounds"]):
        raise HarborError("invalid season replay count")
    if len(canonical(bundles)) > MAX_RECORD_BYTES:
        raise HarborError("season replay input exceeds byte limit")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    source_digest = digest(world)
    for index, bundle in enumerate(bundles):
        verify_bundle(bundle, require_win=True)
        if bundle["source_digest"] != source_digest:
            raise HarborError("season replay source mismatch")
        bundle_digest = bundle["bundle_digest"]
        if bundle_digest in seen:
            raise HarborError("duplicate season game replay")
        seen.add(bundle_digest)
        spec = authored["rounds"][index]
        report = time_trial_report(bundle, spec["course"], require_finish=True)
        medal = report["medal"]
        earned = authored["points"][medal if medal is not None else "finish"]
        total += earned
        results.append({
            "id": spec["id"], "report": report, "points": earned,
            "running_points": total,
        })
    record = {
        "schema": RECORD_SCHEMA, "source": world, "source_digest": source_digest,
        "season": authored, "season_digest": digest(authored),
        "results": results, "next_round": len(results), "total_points": total,
        "complete": len(results) == len(authored["rounds"]),
    }
    record["record_digest"] = digest(record)
    if len(canonical(record)) > MAX_RECORD_BYTES:
        raise HarborError("season record exceeds byte limit")
    return record


def verify_season_record(value: Any) -> dict[str, Any]:
    """Reject resealed fake scores, reordered rounds and forged replay events."""
    _keys(value, RECORD_FIELDS, "season record")
    if value["schema"] != RECORD_SCHEMA or len(canonical(value)) > MAX_RECORD_BYTES:
        raise HarborError("unsupported or oversized season record")
    if value["record_digest"] != digest({
        k: v for k, v in value.items() if k != "record_digest"
    }):
        raise HarborError("season record digest mismatch")
    results = value["results"]
    if not isinstance(results, list) or len(results) > MAX_ROUNDS:
        raise HarborError("invalid season results")
    bundles = []
    for result in results:
        _keys(result, {"id", "report", "points", "running_points"}, "season result")
        report = result["report"]
        if not isinstance(report, dict) or "bundle" not in report:
            raise HarborError("invalid season report")
        bundles.append(report["bundle"])
    rebuilt = build_season(value["source"], value["season"], bundles)
    if rebuilt != value:
        raise HarborError("season replay verification mismatch")
    return {
        "complete": rebuilt["complete"], "next_round": rebuilt["next_round"],
        "total_points": rebuilt["total_points"],
        "record_digest": rebuilt["record_digest"],
    }


def append_season(record: Any, bundle: Any, *, expected_record_digest: str) -> dict[str, Any]:
    """CAS-guarded continuation; reject stale or already-complete season saves."""
    state = verify_season_record(record)
    if expected_record_digest != state["record_digest"]:
        raise HarborError("stale season checkpoint")
    if state["complete"]:
        raise HarborError("season already complete")
    bundles = [entry["report"]["bundle"] for entry in record["results"]]
    bundles.append(bundle)
    return build_season(record["source"], record["season"], bundles)


def season_board(records: Any) -> dict[str, Any]:
    """Recompute deterministic standings; never assert participant identity."""
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_ENTRANTS:
        raise HarborError("invalid season board entrant count")
    if len(canonical(records)) > MAX_BOARD_BYTES:
        raise HarborError("season board input exceeds byte limit")
    source_digest: str | None = None
    season_digest: str | None = None
    seen: set[str] = set()
    ranking: list[dict[str, Any]] = []
    for record in records:
        summary = verify_season_record(record)
        if source_digest is None:
            source_digest, season_digest = record["source_digest"], record["season_digest"]
        if record["source_digest"] != source_digest or record["season_digest"] != season_digest:
            raise HarborError("incompatible season board entry")
        if record["record_digest"] in seen:
            raise HarborError("duplicate season board entry")
        seen.add(record["record_digest"])
        ticks = sum(entry["report"]["finish_tick"] for entry in record["results"])
        ranking.append({
            "record_digest": record["record_digest"], "complete": summary["complete"],
            "rounds": summary["next_round"], "points": summary["total_points"],
            "ticks": ticks,
        })
    ranking.sort(key=lambda item: (
        -int(item["complete"]), -item["rounds"], -item["points"],
        item["ticks"], item["record_digest"],
    ))
    for position, item in enumerate(ranking, 1):
        item["rank"] = position
    board = {
        "schema": BOARD_SCHEMA, "source_digest": source_digest,
        "season_digest": season_digest, "records": deepcopy(records),
        "ranking": ranking,
    }
    board["board_digest"] = digest(board)
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("season board exceeds byte limit")
    return board


def verify_season_board(value: Any) -> list[dict[str, Any]]:
    """Rebuild each participant's replay, points, rank and tie breaker."""
    _keys(value, BOARD_FIELDS, "season board")
    if value["schema"] != BOARD_SCHEMA or len(canonical(value)) > MAX_BOARD_BYTES:
        raise HarborError("unsupported or oversized season board")
    if value["board_digest"] != digest({
        k: v for k, v in value.items() if k != "board_digest"
    }):
        raise HarborError("season board digest mismatch")
    rebuilt = season_board(value["records"])
    if rebuilt != value:
        raise HarborError("season board replay mismatch")
    return deepcopy(rebuilt["ranking"])


def next_season_round(record: Any) -> dict[str, Any]:
    """Return the next real playable authored course, or a completed-season receipt."""
    summary = verify_season_record(record)
    if summary["complete"]:
        return {
            "status": "complete", "next_round": summary["next_round"],
            "total_points": summary["total_points"],
            "record_digest": summary["record_digest"],
            "round": None, "source": None,
        }
    spec = record["season"]["rounds"][summary["next_round"]]
    return {
        "status": "ready", "next_round": summary["next_round"],
        "total_points": summary["total_points"],
        "record_digest": summary["record_digest"],
        "round": deepcopy(spec), "source": deepcopy(record["source"]),
    }
