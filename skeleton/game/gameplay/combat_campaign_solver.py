"""Bounded canonical route search for human-controlled offline combat campaigns.

Search cannot mint rewards or mutate saves. It uses canonical playable
decisions and returns replay-verified portable victory evidence. Exhausted
budgets never imply an authored game is unwinnable.
"""
from __future__ import annotations

import argparse
from collections import deque
from collections.abc import Sequence
import json
import sys
from typing import Any

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_decision_board import decision_board
from skeleton.game.gameplay.combat_campaign_player import (
    _bounded, export_player_campaign, import_player_campaign,
    new_player_campaign, resume_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_route.v1"
MAX_STATES = 256
MAX_DEPTH = 16
MAX_CHOICES = 16
MAX_FRONTIER = 96
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _report_budget(value: Any) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid campaign route JSON") from exc
    if len(encoded) > MAX_REPORT_BYTES:
        raise CombatSessionError("campaign route report exceeds byte budget")


def solve_campaign(*, source: Any = None, session: Any = None,
                   max_states: int = 96, max_depth: int = 12,
                   max_choices: int = 16) -> dict[str, Any]:
    """Search legal canonical hero decisions without modifying the checkpoint."""
    _integer(max_states, "max_states", 1, MAX_STATES)
    _integer(max_depth, "max_depth", 1, MAX_DEPTH)
    _integer(max_choices, "max_choices", 1, MAX_CHOICES)
    if (source is None) == (session is None):
        raise CombatSessionError("provide exactly one campaign source or session")
    start = (new_player_campaign(source) if source is not None
             else verify_player_campaign(session))
    _bounded(start)
    frontier = deque([(start, ())])
    explored = 0
    reasons: set[str] = set()
    victory = None
    victory_actions: tuple[dict[str, Any], ...] = ()
    while frontier:
        if explored >= max_states:
            reasons.add("state_budget")
            break
        current, path = frontier.popleft()
        explored += 1
        phase = current["state"]["phase"]
        if phase == "won":
            victory, victory_actions = current, path
            break
        if phase != "active":
            continue
        if len(path) >= max_depth:
            reasons.add("depth_budget")
            continue
        board = decision_board(current, max_choices=max_choices)
        if board["choices_truncated"]:
            reasons.add("choice_budget")
        for preview in board["choices"]:
            following = resume_player_campaign(current, [preview["action"]])
            if (following["state_digest"] != preview["state_digest"]
                    or dig(following["save"]) != preview["save_digest"]):
                raise CombatSessionError("canonical decision board diverged")
            if len(frontier) >= min(max_states, MAX_FRONTIER):
                reasons.add("frontier_budget")
                continue
            frontier.append((following, (*path, preview["action"])))
    if victory is not None:
        replayed = resume_player_campaign(start, list(victory_actions))
        if replayed != victory or replayed["state"]["phase"] != "won":
            raise CombatSessionError("campaign victory witness failed replay")
        portable = export_player_campaign(replayed)
        if import_player_campaign(portable) != replayed:
            raise CombatSessionError("campaign victory export failed replay")
    else:
        replayed = None
        portable = None
    result = {
        "schema_version": SCHEMA,
        "source_digest": start["source_digest"],
        "start_state_digest": start["state_digest"],
        "start_session": start,
        "limits": {"max_states": max_states, "max_depth": max_depth,
                   "max_choices": max_choices, "max_frontier": MAX_FRONTIER},
        "explored_states": explored,
        "status": ("solved" if victory is not None else
                   "inconclusive" if reasons else "no_victory_in_explored_graph"),
        "incomplete_reasons": sorted(reasons),
        "actions": list(victory_actions) if victory is not None else [],
        "terminal_session": replayed,
        "portable_bundle": portable,
        "proof_kind": "canonical_replay_not_signature_or_unwinnability_proof",
    }
    result["receipt"] = dig(result)
    _report_budget(result)
    return result


def verify_campaign_route(raw: Any, *,
                          expected_source_digest: str | None = None) -> dict[str, Any]:
    """Recompute untrusted search receipts, gameplay and portable victory."""
    _report_budget(raw)
    obj = _object(raw, {
        "schema_version", "source_digest", "start_state_digest",
        "start_session", "limits", "explored_states", "status",
        "incomplete_reasons", "actions", "terminal_session",
        "portable_bundle", "proof_kind", "receipt",
    }, "campaign route report")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign route schema")
    if (expected_source_digest is not None
            and (type(expected_source_digest) is not str
                 or obj["source_digest"] != expected_source_digest)):
        raise CombatSessionError("stale campaign route source lease")
    limits = _object(obj["limits"], {
        "max_states", "max_depth", "max_choices", "max_frontier",
    }, "campaign route limits")
    if limits["max_frontier"] != MAX_FRONTIER:
        raise CombatSessionError("campaign route frontier policy mismatch")
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("campaign route receipt mismatch")
    start = verify_player_campaign(obj["start_session"])
    expected = solve_campaign(
        session=start, max_states=limits["max_states"],
        max_depth=limits["max_depth"], max_choices=limits["max_choices"],
    )
    if expected != obj:
        raise CombatSessionError("campaign route source, replay or witness mismatch")
    if expected["status"] == "solved":
        replayed = resume_player_campaign(start, expected["actions"])
        if (replayed != expected["terminal_session"]
                or import_player_campaign(expected["portable_bundle"]) != replayed):
            raise CombatSessionError("campaign route portable replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Find an original replayable campaign victory")
    solve = sub.add_parser("solve")
    source = solve.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-json")
    source.add_argument("--session-json")
    solve.add_argument("--max-states", type=int, default=96)
    solve.add_argument("--max-depth", type=int, default=12)
    solve.add_argument("--max-choices", type=int, default=16)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    verify.add_argument("--expected-source-digest")
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = solve_campaign(source=original_campaign())
        elif args.command == "solve":
            result = solve_campaign(
                source=(_parse_json(args.source_json, "campaign source")
                        if args.source_json is not None else None),
                session=(_parse_json(args.session_json, "campaign session")
                         if args.session_json is not None else None),
                max_states=args.max_states, max_depth=args.max_depth,
                max_choices=args.max_choices,
            )
        else:
            result = verify_campaign_route(
                _parse_json(args.report_json, "campaign route report"),
                expected_source_digest=args.expected_source_digest,
            )
        _report_budget(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
