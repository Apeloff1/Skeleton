"""Replay-backed multi-season coaching roadmap with bounded beam exploration.

Every candidate season is played by the existing deterministic league engine.
The roadmap is an advisory witness, not a claim of globally optimal coaching
or authority to mint wins, training tokens or rewards.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_league import _bounded, _json, standings
from skeleton.game.gameplay.combat_league_career import (
    _advance_verified, export_career, finish_career, import_career,
    new_career, original_career, verify_career,
)
from skeleton.game.gameplay.combat_league_career_advice import _candidates
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id

SCHEMA = "skeleton.combat_career_roadmap.v1"
MAX_BEAM = 8
MAX_EXPANSIONS = 128


def _score(saved: dict[str, Any], target: str,
           choices: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    state = saved["state"]
    journal = state["season_journal"]
    points = 0
    if journal:
        board = standings(journal[-1]["league"])
        points = next(row["points"] for row in board["ranking"]
                      if row["entrant_id"] == target)
    return (
        state["wins"][target], points, state["tokens_remaining"],
        -sum(choice["kind"] == "train" for choice in choices),
    )


def _report(start: dict[str, Any], target: str,
            terminal: dict[str, Any] | None, choices: list[dict[str, Any]],
            expansions: int, beam: int, budget: int,
            reason: str) -> dict[str, Any]:
    completed = terminal is not None and terminal["state"]["phase"] != "active"
    bundle = export_career(terminal) if completed else None
    report = {
        "schema_version": SCHEMA,
        "status": "replayable_advice" if completed else "inconclusive",
        "reason": "bounded_beam_candidate" if completed else reason,
        "source_digest": start["source_digest"],
        "starting_state_digest": start["state_digest"],
        "starting_save_digest": dig(start["save"]),
        "target_id": target,
        "choices": choices if completed else [],
        "seasons_remaining": (
            start["source"]["seasons"] - start["state"]["next_season"]
        ),
        "terminal_state_digest": terminal["state_digest"] if completed else None,
        "terminal_save_digest": dig(terminal["save"]) if completed else None,
        "predicted_champion": terminal["state"]["champion"] if completed else None,
        "target_champion": (
            terminal["state"]["champion"] == target if completed else None
        ),
        "portable_bundle": bundle,
        "expansions": expansions, "beam_width": beam,
        "expansion_budget": budget,
        "qualification": "replayed_bounded_advice_not_global_optimum",
    }
    report["receipt"] = dig(report)
    _bounded(report)
    return report


def plan_career(raw: Any, target_id: Any, *,
                beam_width: int = 3,
                max_expansions: int = 64) -> dict[str, Any]:
    if type(beam_width) is not int or not 1 <= beam_width <= MAX_BEAM:
        raise CombatSessionError("invalid career roadmap beam width")
    if (type(max_expansions) is not int
            or not 1 <= max_expansions <= MAX_EXPANSIONS):
        raise CombatSessionError("invalid career roadmap expansion budget")
    start = verify_career(raw)
    target = _id(target_id, "target_id")
    if target not in start["state"]["wins"]:
        raise CombatSessionError("career roadmap target not authored")
    if start["state"]["phase"] != "active":
        return _report(start, target, start, [], 0, beam_width,
                       max_expansions, "")
    beam: list[tuple[dict[str, Any], list[dict[str, Any]]]] = [(start, [])]
    expansions = 0
    seasons = start["source"]["seasons"] - start["state"]["next_season"]
    for _ in range(seasons):
        successors: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for current, choices in beam:
            for choice in _candidates(current, target):
                if expansions >= max_expansions:
                    return _report(start, target, None, [], expansions,
                                   beam_width, max_expansions,
                                   "expansion_budget_exhausted")
                expansions += 1
                try:
                    next_saved = _advance_verified(current, choice)
                except CombatSessionError:
                    # Only an attempted training of an already-capped stat
                    # is an expected invalid candidate; propagate all else.
                    if choice["kind"] == "train":
                        entrant = next(
                            entry for entry in current["source"]["league"]["entrants"]
                            if entry["id"] == target
                        )
                        cap = 10000 if choice["stat"] == "max_hp" else 1000
                        if entrant[choice["stat"]] >= cap:
                            continue
                    raise
                successors.append((next_saved, [*choices, choice]))
        if not successors:
            return _report(start, target, None, [], expansions,
                           beam_width, max_expansions, "no_legal_coaching_choice")
        # Stable ordering makes ties deterministic and never relies on
        # object iteration, random sampling or provider predictions.
        successors.sort(
            key=lambda pair: (
                tuple(-x for x in _score(pair[0], target, pair[1])),
                json.dumps(pair[1], sort_keys=True),
            )
        )
        beam = successors[:beam_width]
    terminal, choices = beam[0]
    # Independent replay from the original checkpoint proves every season,
    # nested tournament and training token, not just the beam's local state.
    replay = finish_career(start["source"], choices, resume=start)
    if replay != terminal or import_career(export_career(replay)) != replay:
        raise CombatSessionError("career roadmap replay or export mismatch")
    return _report(start, target, replay, choices, expansions,
                   beam_width, max_expansions, "")


def verify_career_roadmap(raw: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise CombatSessionError("invalid career roadmap")
    expected = plan_career(
        raw, report.get("target_id"),
        beam_width=report.get("beam_width"),
        max_expansions=report.get("expansion_budget"),
    )
    if expected != report:
        raise CombatSessionError("career roadmap witness mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-career-roadmap")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    plan = sub.add_parser("plan")
    verify = sub.add_parser("verify")
    for item in (demo, plan):
        item.add_argument("--beam-width", type=int, default=3)
        item.add_argument("--max-expansions", type=int, default=64)
    demo.add_argument("--target-id", default="amber_guard")
    plan.add_argument("--target-id", required=True)
    plan.add_argument("--session-json", required=True)
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = plan_career(
                new_career(original_career()), args.target_id,
                beam_width=args.beam_width,
                max_expansions=args.max_expansions,
            )
        elif args.command == "plan":
            result = plan_career(
                _json(args.session_json, "career save"), args.target_id,
                beam_width=args.beam_width,
                max_expansions=args.max_expansions,
            )
        else:
            result = verify_career_roadmap(
                _json(args.session_json, "career save"),
                _json(args.report_json, "career roadmap"),
            )
        print(_bounded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, KeyError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
