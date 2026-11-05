"""Source-bound, replay-verified exploration and fog-of-war gameplay.

Visits are awarded only for real positions reached by canonical movement. The
report contains the original event chain, a deterministic map reveal, and
portable CAS custody; its digest is integrity evidence, not a signature.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, step, validate_source,
    verify_bundle,
)
from .harbor_crafting_sessions import resume_bundle

BOARD_SCHEMA = "skeleton.game.harbor.survey-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.survey-report.v1"
MAX_BOARD_BYTES = 16384
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 3
MAX_SITES = 12
BOARD_FIELDS = {"schema", "source_id", "reveal_radius", "sites", "minimum_points"}
REPORT_FIELDS = {
    "schema", "source", "board", "source_digest", "board_digest",
    "bundle", "seen_tiles", "visits", "score", "complete",
    "ending", "report_digest",
}


def validate_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_FIELDS, "survey board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("survey board source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("survey board exceeds byte limit")
    _integer(board["reveal_radius"], 0, 3, "survey reveal radius")
    sites = board["sites"]
    if not isinstance(sites, list) or not 1 <= len(sites) <= MAX_SITES:
        raise HarborError("invalid survey sites")
    ids: set[str] = set()
    locations: set[tuple[int, int]] = set()
    points = 0
    required = 0
    for site in sites:
        _keys(site, {"id", "at", "points", "required"}, "survey site")
        name = _identifier(site["id"], "survey site id")
        pos = site["at"]
        if not isinstance(pos, list) or len(pos) != 2:
            raise HarborError("invalid survey coordinate")
        x = _integer(pos[0], 0, len(world["map"][0]) - 1, "survey x")
        y = _integer(pos[1], 0, len(world["map"]) - 1, "survey y")
        if world["map"][y][x] != ".":
            raise HarborError("survey site is blocked")
        if name in ids or (x, y) in locations:
            raise HarborError("duplicate survey site")
        if type(site["required"]) is not bool:
            raise HarborError("invalid survey required flag")
        points += _integer(site["points"], 1, 32, "survey points")
        required += site["required"]
        ids.add(name)
        locations.add((x, y))
    if not required:
        raise HarborError("survey needs a required site")
    _integer(board["minimum_points"], 1, points, "survey minimum points")
    return deepcopy(board)


def _trace(world: dict[str, Any], board: dict[str, Any],
           actions: list[Any]) -> tuple[list[list[int]], list[dict[str, Any]], int]:
    state = initial_state(world)
    seen: set[tuple[int, int]] = set()
    awarded: set[str] = set()
    visits: list[dict[str, Any]] = []
    score = 0
    radius = board["reveal_radius"]

    def observe() -> None:
        nonlocal score
        x, y = state["pos"]
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius:
                    continue
                px, py = x + dx, y + dy
                if 0 <= py < len(world["map"]) and 0 <= px < len(world["map"][0]):
                    seen.add((px, py))
        for site in board["sites"]:
            if site["id"] not in awarded and site["at"] == state["pos"]:
                awarded.add(site["id"])
                score += site["points"]
                visits.append({
                    "id": site["id"], "tick": state["tick"],
                    "at": list(state["pos"]), "points": site["points"],
                })

    observe()
    for action in actions:
        state = step(world, state, action)
        observe()
    return [[x, y] for x, y in sorted(seen, key=lambda p: (p[1], p[0]))], visits, score


def build_survey(source: Any, board: Any, actions: Any,
                 *, require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_board(board, world)
    bundle = export_bundle(world, actions)
    seen, visits, score = _trace(world, authored, [e["action"] for e in bundle["events"]])
    visited = {entry["id"] for entry in visits}
    complete = (
        bundle["state"]["ending"] is not None
        and score >= authored["minimum_points"]
        and all(site["id"] in visited for site in authored["sites"] if site["required"])
    )
    if require_complete and not complete:
        raise HarborError("survey victory not earned")
    report = {
        "schema": REPORT_SCHEMA, "source": world, "board": authored,
        "source_digest": digest(world), "board_digest": digest(authored),
        "bundle": bundle, "seen_tiles": seen, "visits": visits,
        "score": score, "complete": complete,
        "ending": bundle["state"]["ending"],
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("survey report exceeds byte limit")
    return report


def verify_survey(report: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "survey report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized survey report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("survey report digest mismatch")
    verify_bundle(report["bundle"])
    actions = [event["action"] for event in report["bundle"]["events"]]
    rebuilt = build_survey(report["source"], report["board"], actions,
                           require_complete=require_complete)
    if rebuilt != report:
        raise HarborError("survey replay mismatch")
    return {
        "complete": rebuilt["complete"], "score": rebuilt["score"],
        "visited": [entry["id"] for entry in rebuilt["visits"]],
        "terminal_digest": rebuilt["bundle"]["terminal_digest"],
        "report_digest": rebuilt["report_digest"],
    }


def resume_survey(report: Any, actions: Any, *, expected_digest: str,
                  require_complete: bool = False) -> dict[str, Any]:
    status = verify_survey(report)
    if type(expected_digest) is not str or expected_digest != status["report_digest"]:
        raise HarborError("stale survey checkpoint")
    if report["bundle"]["state"]["ending"] is not None:
        raise HarborError("survey campaign already complete")
    advanced = resume_bundle(
        report["bundle"], actions,
        expected_terminal_digest=report["bundle"]["terminal_digest"],
    )
    all_actions = [event["action"] for event in advanced["events"]]
    rebuilt = build_survey(report["source"], report["board"], all_actions,
                           require_complete=require_complete)
    if rebuilt["bundle"]["events"][:len(report["bundle"]["events"])] != report["bundle"]["events"]:
        raise HarborError("survey history rewritten")
    return rebuilt
