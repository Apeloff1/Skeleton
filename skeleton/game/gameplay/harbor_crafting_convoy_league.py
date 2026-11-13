"""Original multi-contract convoy league: earned progression, replay and CAS custody.

Each round replays the canonical player movement/crafting/combat engine.
Rounds intentionally reset their inventory; league scores never mint world items.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, _identifier, _integer, _keys, canonical, digest, validate_source,
)
from .harbor_crafting_convoy import (
    MAX_REPORT_BYTES as MAX_CONVOY_REPORT_BYTES, build_convoy,
    validate_convoy_board, verify_convoy,
)

LEAGUE_SCHEMA = "skeleton.game.harbor.convoy-league.v1"
SAVE_SCHEMA = "skeleton.game.harbor.convoy-league-save.v1"
MAX_LEAGUE_BYTES = 262144
MAX_SAVE_BYTES = 8 * MAX_CONVOY_REPORT_BYTES + MAX_LEAGUE_BYTES
MAX_ROUNDS = 8
LEAGUE_FIELDS = {"schema", "source_id", "rounds", "target_score", "max_total_ticks"}
ROUND_FIELDS = {"id", "board", "minimum_bounty", "minimum_hull"}
SAVE_FIELDS = {
    "schema", "source", "league", "sessions", "reports", "standings",
    "score", "complete", "failed", "source_digest", "league_digest", "save_digest",
}


def validate_league(league: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(league, LEAGUE_FIELDS, "convoy league")
    if league["schema"] != LEAGUE_SCHEMA or league["source_id"] != world["id"]:
        raise HarborError("convoy league source mismatch")
    if len(canonical(league)) > MAX_LEAGUE_BYTES:
        raise HarborError("convoy league exceeds byte budget")
    rounds = league["rounds"]
    if not isinstance(rounds, list) or not 2 <= len(rounds) <= MAX_ROUNDS:
        raise HarborError("invalid convoy league round count")
    _integer(league["target_score"], 1, MAX_ROUNDS * 200, "league target score")
    _integer(
        league["max_total_ticks"], 1, MAX_ROUNDS * world["max_ticks"],
        "league tick budget",
    )
    names: set[str] = set()
    boards: set[str] = set()
    for round_ in rounds:
        _keys(round_, ROUND_FIELDS, "league round")
        name = _identifier(round_["id"], "league round id")
        if name in names:
            raise HarborError("duplicate league round id")
        names.add(name)
        board = validate_convoy_board(round_["board"], world)
        board_hash = digest(board)
        if board_hash in boards:
            raise HarborError("duplicate league board")
        boards.add(board_hash)
        _integer(round_["minimum_bounty"], 0, 1200, "league bounty requirement")
        _integer(round_["minimum_hull"], 1, board["hull"], "league hull requirement")
    return deepcopy(league)


def build_league(source: Any, league: Any, sessions: Any, *,
                 require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_league(league, world)
    if not isinstance(sessions, list) or len(sessions) > len(authored["rounds"]):
        raise HarborError("invalid convoy league sessions")
    reports: list[dict[str, Any]] = []
    standings: list[dict[str, Any]] = []
    score = 0
    total_ticks = 0
    failed = False
    normalized_sessions: list[list[dict[str, str]]] = []
    for index, actions in enumerate(sessions):
        if failed or (index and not standings[-1]["earned"]):
            raise HarborError("cannot start next league round before earned victory")
        if not isinstance(actions, list) or not actions:
            raise HarborError("league round requires player actions")
        rule = authored["rounds"][index]
        report = build_convoy(world, rule["board"], actions)
        state = report["state"]
        total_ticks += state["tick"]
        if total_ticks > authored["max_total_ticks"]:
            raise HarborError("league tick budget exhausted")
        earned = bool(
            state["complete"]
            and state["bounty"] >= rule["minimum_bounty"]
            and state["hull"] >= rule["minimum_hull"]
        )
        points = state["bounty"] + state["hull"] * 2 if earned else 0
        score += points
        failed = bool(
            state["failed"] or (
                state["complete"] and not earned
            )
        )
        standings.append({
            "round": rule["id"], "earned": earned, "complete": state["complete"],
            "failed": failed, "points": points, "hull": state["hull"],
            "bounty": state["bounty"], "ticks": state["tick"],
            "report_digest": report["report_digest"],
        })
        reports.append(report)
        normalized_sessions.append(deepcopy(report["actions"]))
    all_earned = (
        len(standings) == len(authored["rounds"])
        and all(row["earned"] for row in standings)
    )
    complete = all_earned and score >= authored["target_score"]
    if all_earned and not complete:
        failed = True
    if require_complete and not complete:
        raise HarborError("convoy league championship not earned")
    save = {
        "schema": SAVE_SCHEMA, "source": deepcopy(world), "league": authored,
        "sessions": normalized_sessions, "reports": reports,
        "standings": standings, "score": score,
        "complete": complete, "failed": failed,
        "source_digest": digest(world), "league_digest": digest(authored),
    }
    save["save_digest"] = digest(save)
    if len(canonical(save)) > MAX_SAVE_BYTES:
        raise HarborError("convoy league save exceeds byte budget")
    return save


def verify_league(save: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(save, SAVE_FIELDS, "convoy league save")
    if save["schema"] != SAVE_SCHEMA or len(canonical(save)) > MAX_SAVE_BYTES:
        raise HarborError("unsupported or oversized convoy league save")
    if save["save_digest"] != digest({
        key: value for key, value in save.items() if key != "save_digest"
    }):
        raise HarborError("convoy league save digest mismatch")
    if not isinstance(save["reports"], list) or not isinstance(save["sessions"], list):
        raise HarborError("invalid league save sessions or reports")
    for report in save["reports"]:
        verify_convoy(report)
    rebuilt = build_league(
        save["source"], save["league"], save["sessions"],
        require_complete=require_complete,
    )
    if rebuilt != save:
        raise HarborError("convoy league replay mismatch")
    return {
        "verified": True, "complete": rebuilt["complete"],
        "failed": rebuilt["failed"], "score": rebuilt["score"],
        "rounds_played": len(rebuilt["reports"]),
        "rounds_total": len(rebuilt["league"]["rounds"]),
        "save_digest": rebuilt["save_digest"],
    }


def league_status(save: Any) -> dict[str, Any]:
    summary = verify_league(save)
    rounds = save["league"]["rounds"]
    reports = save["reports"]
    if summary["complete"] or summary["failed"]:
        next_round = None
    elif reports and not reports[-1]["state"]["complete"]:
        next_round = rounds[len(reports) - 1]["id"]
    else:
        next_round = rounds[len(reports)]["id"]
    return {
        **summary, "next_round": next_round,
        "target_score": save["league"]["target_score"],
        "standings": deepcopy(save["standings"]),
    }


def resume_league(save: Any, actions: Any, *, expected_digest: str,
                  require_complete: bool = False) -> dict[str, Any]:
    verify_league(save)
    if type(expected_digest) is not str or expected_digest != save["save_digest"]:
        raise HarborError("stale convoy league checkpoint")
    if save["complete"] or save["failed"]:
        raise HarborError("terminal convoy league checkpoint")
    if not isinstance(actions, list) or not actions:
        raise HarborError("league continuation requires actions")
    sessions = deepcopy(save["sessions"])
    if sessions and not save["reports"][-1]["state"]["complete"]:
        sessions[-1] += actions
    else:
        sessions.append(actions)
    result = build_league(
        save["source"], save["league"], sessions, require_complete=require_complete,
    )
    if result["reports"][:max(0, len(save["reports"]) - 1)] != save["reports"][:max(0, len(save["reports"]) - 1)]:
        raise HarborError("league continuation rewrote completed rounds")
    if save["reports"] and not save["reports"][-1]["state"]["complete"]:
        old = save["reports"][-1]["events"]
        if result["reports"][-1]["events"][:len(old)] != old:
            raise HarborError("league continuation rewrote active round")
    return result
