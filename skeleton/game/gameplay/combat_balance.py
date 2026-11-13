"""Bounded, replay-verifiable combat encounter balance and victory witnesses.

This is a deterministic authoring diagnostic, not a trusted proof of game
fairness. It models one human-controlled team against the versioned canonical
offline tactical policy; it does not run user-authored code or use a provider.
An exhausted search proves only the stated, bounded policy/game contract.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _active_actor, _advance, _id, _integer,
    _object, _parse_json, new_session, normalize_scenario,
    original_demo, resume_session, verify_session,
)
from skeleton.game.gameplay.tactical_policy import (
    POLICY_VERSION, _decide_verified,
)

SCHEMA = "skeleton.combat_balance.v1"
MAX_STATES = 4096
MAX_ANALYSIS_TURNS = 32
MAX_TRANSITIONS = MAX_STATES * 18


def _team(scenario: dict[str, Any], requested: Any) -> str:
    team = _id(requested, "player team")
    if team not in {actor["team"] for actor in scenario["actors"]}:
        raise CombatSessionError("player team not in authored scenario")
    return team


def _actions(session: dict[str, Any], team: str) -> list[dict[str, str]]:
    """Enumerate all legal actions for a human, otherwise the fixed AI policy."""
    spec = session["scenario"]
    state = session["state"]
    actor_id, _ = _active_actor(spec, state)
    actors = {actor["id"]: actor for actor in spec["actors"]}
    if actors[actor_id]["team"] != team:
        return [_decide_verified(session)]
    attacks = [
        {"kind": "attack", "actor_id": actor_id, "target_id": target}
        for target in sorted(actors)
        if actors[target]["team"] != team
        and state["actors"][target]["hp"] > 0
    ]
    # Attacks first makes the first discovered shortest victory easy to replay.
    return [*attacks, {"kind": "guard", "actor_id": actor_id},
            {"kind": "rest", "actor_id": actor_id}]


def _report(
    spec: dict[str, Any], team: str, max_states: int, max_turns: int,
    status: str, explored: int, transitions: int,
    witness: dict[str, Any] | None,
) -> dict[str, Any]:
    actions = (
        [entry["action"] for entry in witness["journal"]]
        if witness is not None else None
    )
    report = {
        "schema_version": SCHEMA,
        "scenario": spec,
        "source_digest": dig(spec),
        "team": team,
        "opponent_policy": POLICY_VERSION,
        "max_states": max_states,
        "max_turns": max_turns,
        "status": status,
        "explored_states": explored,
        "transitions": transitions,
        "witness_actions": actions,
        "witness_state_digest": (
            witness["state_digest"] if witness is not None else None
        ),
        "witness_save_digest": (
            dig(witness["save"]) if witness is not None else None
        ),
    }
    report["checksum"] = dig(report)
    return report


def analyze(
    scenario: Any, team: Any, *, max_states: int = 512,
    max_turns: int = 16,
) -> dict[str, Any]:
    """Find a shortest victory or conservatively label a bounded search.

    A returned witness is verified by canonical engine replay. A no-witness
    result is exhaustive ONLY if no state, turn, or transition budget was hit.
    The opponent follows the canonical deterministic tactical policy.
    """
    spec = normalize_scenario(scenario)
    team = _team(spec, team)
    states = _integer(max_states, "max_states", 1, MAX_STATES)
    turns = _integer(max_turns, "max_turns", 1, MAX_ANALYSIS_TURNS)
    root = new_session(spec)
    pending = deque([root])
    seen = {root["state_digest"]}
    explored = 0
    transitions = 0
    incomplete = False
    while pending:
        if explored >= states:
            incomplete = True
            break
        current = pending.popleft()
        explored += 1
        phase = current["state"]["phase"]
        if phase == "won" and current["state"]["winner"] == team:
            verified = verify_session(current)
            return _report(spec, team, states, turns, "victory_witness",
                           explored, transitions, verified)
        if phase != "active":
            continue
        if current["state"]["tick"] >= turns:
            incomplete = True
            continue
        for action in _actions(current, team):
            if transitions >= MAX_TRANSITIONS:
                incomplete = True
                pending.clear()
                break
            successor = _advance(current, action)
            transitions += 1
            if (successor["state"]["phase"] == "won"
                    and successor["state"]["winner"] == team):
                verified = verify_session(successor)
                return _report(spec, team, states, turns, "victory_witness",
                               explored, transitions, verified)
            digest = successor["state_digest"]
            if digest not in seen:
                seen.add(digest)
                pending.append(successor)
    status = "inconclusive_budget" if incomplete else "exhaustive_no_witness"
    return _report(spec, team, states, turns, status,
                   explored, transitions, None)


def verify_report(payload: Any) -> dict[str, Any]:
    """Re-run the complete bounded search; reject forged victory or exhaustion."""
    fields = {
        "schema_version", "scenario", "source_digest", "team",
        "opponent_policy", "max_states", "max_turns", "status",
        "explored_states", "transitions", "witness_actions",
        "witness_state_digest", "witness_save_digest", "checksum",
    }
    report = _object(payload, fields, "combat balance report")
    if report["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported balance report schema")
    if report["opponent_policy"] != POLICY_VERSION:
        raise CombatSessionError("unsupported opponent policy")
    expected = analyze(
        report["scenario"], report["team"],
        max_states=report["max_states"], max_turns=report["max_turns"],
    )
    if report != expected:
        raise CombatSessionError("balance report replay or checksum mismatch")
    if report["status"] == "victory_witness":
        replay = resume_session(new_session(report["scenario"]),
                                report["witness_actions"])
        if (replay["state"]["phase"] != "won"
                or replay["state"]["winner"] != report["team"]
                or replay["state_digest"] != report["witness_state_digest"]
                or dig(replay["save"]) != report["witness_save_digest"]):
            raise CombatSessionError("balance victory witness replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton combat-balance",
        description="Bounded offline combat victory analysis and replay receipts",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Analyze original two-team authored encounter")
    check = sub.add_parser("analyze", help="Analyze a canonical authored encounter")
    check.add_argument("--scenario-json", required=True)
    check.add_argument("--team", required=True)
    check.add_argument("--max-states", type=int, default=512)
    check.add_argument("--max-turns", type=int, default=16)
    verify = sub.add_parser("verify", help="Recompute a serialized analysis report")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            scenario, _ = original_demo()
            result = analyze(scenario, "wayfarers")
        elif args.command == "analyze":
            result = analyze(
                _parse_json(args.scenario_json, "combat scenario"),
                args.team, max_states=args.max_states,
                max_turns=args.max_turns,
            )
        else:
            result = verify_report(_parse_json(args.report_json, "balance report"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=False))
        return 0
    except (CombatSessionError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
