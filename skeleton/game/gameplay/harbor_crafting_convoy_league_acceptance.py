"""One-command source-to-victory league acceptance with independently replayed proof."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy_league import validate_league, verify_league
from .harbor_crafting_convoy_league_solver import solve_league, verify_league_plan
from .harbor_crafting_convoy_league_package import (
    build_league_package, play_league_package, verify_league_package_play,
)
from .harbor_crafting_convoy_league_journal import (
    append_league_journal, create_league_journal, verify_league_journal,
)
from .harbor_crafting_convoy_league_board import (
    build_league_leaderboard, verify_league_leaderboard,
)

SCHEMA = "skeleton.game.harbor.convoy-league-acceptance.v1"
MAX_ACCEPT_BYTES = 262144
FIELDS = {
    "schema", "source", "league", "sessions", "plan_digest", "package_digest",
    "play_digest", "journal_digest", "board_digest", "summary", "acceptance_digest",
}


def accept_league(source: Any, league: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_league(league, world)
    plan = solve_league(world, authored)
    verify_league_plan(plan)
    sessions = [deepcopy(round_plan["actions"]) for round_plan in plan["plans"]]
    package = build_league_package("lantern_quay_championship", world, authored)
    play = play_league_package(package, sessions, require_complete=True)
    verify_league_package_play(play, require_complete=True)
    if play["save"] != plan["save"]:
        raise HarborError("league acceptance package and solver divergence")
    journal = create_league_journal(package)
    for session in sessions:
        for index in range(0, len(session), 32):
            journal = append_league_journal(
                journal, session[index:index + 32],
                expected_digest=journal["journal_digest"],
            )
    journal_status = verify_league_journal(journal)
    if not journal_status["complete"] or journal_status["head"] != play["play_digest"]:
        raise HarborError("league acceptance journal replay divergence")
    leaderboard = build_league_leaderboard([
        {"id": "lantern_quay_player", "save": play["save"]}
    ])
    verify_league_leaderboard(leaderboard)
    summary = {
        "complete": True, "score": play["save"]["score"],
        "rounds": len(sessions), "ticks": sum(len(a) for a in sessions),
        "journal_entries": journal_status["entries"],
    }
    acceptance = {
        "schema": SCHEMA, "source": world, "league": authored,
        "sessions": sessions, "plan_digest": plan["plan_digest"],
        "package_digest": package["package_digest"],
        "play_digest": play["play_digest"],
        "journal_digest": journal["journal_digest"],
        "board_digest": leaderboard["board_digest"],
        "summary": summary,
    }
    acceptance["acceptance_digest"] = digest(acceptance)
    if len(canonical(acceptance)) > MAX_ACCEPT_BYTES:
        raise HarborError("league acceptance exceeds byte budget")
    return acceptance


def verify_league_acceptance(acceptance: Any) -> dict[str, Any]:
    _keys(acceptance, FIELDS, "league acceptance")
    if acceptance["schema"] != SCHEMA or len(canonical(acceptance)) > MAX_ACCEPT_BYTES:
        raise HarborError("unsupported or oversized league acceptance")
    if acceptance["acceptance_digest"] != digest({
        key: value for key, value in acceptance.items() if key != "acceptance_digest"
    }):
        raise HarborError("league acceptance digest mismatch")
    rebuilt = accept_league(acceptance["source"], acceptance["league"])
    if rebuilt != acceptance:
        raise HarborError("league acceptance replay mismatch")
    return {"verified": True, **deepcopy(rebuilt["summary"]),
            "acceptance_digest": rebuilt["acceptance_digest"]}
