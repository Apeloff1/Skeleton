"""End-to-end offline capture-game acceptance: edit -> solve -> play -> save -> export.

This is a reproducible gameplay witness, not a release/device certificate.
Every transition uses the same canonical source, movement and replay checks.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import (
    _encoded, normalize_control, original_actions, original_control,
    package_control, verify_control_package,
)
from skeleton.game.gameplay.arena_control_author import author_control
from skeleton.game.gameplay.arena_control_campaign import (
    SCHEMA as CAMPAIGN_SCHEMA, package_campaign, play_campaign,
    verify_package,
)
from skeleton.game.gameplay.arena_control_interactive import play_interactive
from skeleton.game.gameplay.arena_control_solver import (
    solve_control, verify_solution,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_acceptance.v1"


def accept_control(source: Any, team: Any, operations: Any,
                   preview_actions: Any, *, max_nodes: int = 256) -> dict[str, Any]:
    original = normalize_control(source)
    selected = _id(team, "team")
    nodes = _integer(max_nodes, "max_nodes", 1, 256)
    authored = author_control(original, operations, dig(original), preview_actions)
    compiled = authored["source"]
    search = solve_control(compiled, selected, max_nodes=nodes)
    if search["status"] != "solved":
        result = {
            "schema_version": SCHEMA,
            "status": "unproven_within_budget",
            "claim": "bounded_offline_search_not_release_certification",
            "source": original, "team": selected,
            "operations": authored["operations"],
            "preview_actions": authored["preview_actions"],
            "max_nodes": nodes, "author_receipt": authored,
            "solver_receipt": search, "interactive": None,
            "control_package": None, "campaign_package": None,
        }
        result["receipt"] = dig(result)
        _encoded(result)
        return result
    verified = verify_solution(search)
    actions = verified["actions"]
    stats = {actor["id"]: actor["team"] for actor in compiled["arena"]["actors"]}
    player_actions = [
        action for action in actions if stats[action["actor_id"]] == selected
    ]
    input_text = "".join(_encoded(action) + "\n" for action in player_actions)
    output = io.StringIO()
    played = play_interactive(
        compiled, selected,
        input_stream=io.StringIO(input_text), output_stream=output,
        max_inputs=max(1, len(player_actions)),
    )
    if played["status"] != "completed" or played["session"] != verified["terminal"]:
        raise CombatSessionError("offline interactive replay differs from solver witness")
    control_package = package_control(played["session"])
    verify_control_package(control_package)
    campaign_source = {
        "schema_version": CAMPAIGN_SCHEMA,
        "campaign_id": compiled["control_id"] + "_acceptance",
        "world_id": compiled["arena"]["world_id"],
        "player_team": selected, "required_wins": 1,
        "stages": [{"control": compiled, "reward": 1}],
    }
    campaign = play_campaign(campaign_source, [actions])
    if campaign["state"]["phase"] != "won" or campaign["state"]["currency"] != 1:
        raise CombatSessionError("offline campaign reward witness not earned")
    campaign_package = package_campaign(campaign)
    verify_package(campaign_package)
    result = {
        "schema_version": SCHEMA,
        "status": "passed_offline_gameplay_witness",
        "claim": "deterministic_offline_acceptance_not_device_certification",
        "source": original, "team": selected,
        "operations": authored["operations"],
        "preview_actions": authored["preview_actions"],
        "max_nodes": nodes, "author_receipt": authored,
        "solver_receipt": verified,
        "interactive": {
            "status": played["status"], "session_digest": played["session_digest"],
            "events": [json.loads(line) for line in output.getvalue().splitlines()],
        },
        "control_package": control_package,
        "campaign_package": campaign_package,
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_acceptance(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "status", "claim", "source", "team",
        "operations", "preview_actions", "max_nodes",
        "author_receipt", "solver_receipt", "interactive",
        "control_package", "campaign_package", "receipt",
    }, "control-point acceptance receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point acceptance receipt")
    _encoded(obj)
    expected = accept_control(
        obj["source"], obj["team"], obj["operations"],
        obj["preview_actions"], max_nodes=obj["max_nodes"],
    )
    if expected != obj:
        raise CombatSessionError("control-point acceptance or replay mismatch")
    return expected


def original_acceptance_demo() -> dict[str, Any]:
    return accept_control(
        original_control(), "wayfarers",
        [{"kind": "set-score-target", "value": 1}],
        original_actions()[:1],
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Replay complete original game-production vertical")
    accept = sub.add_parser("accept")
    accept.add_argument("--source-json", required=True)
    accept.add_argument("--team", required=True)
    accept.add_argument("--operations-json", required=True)
    accept.add_argument("--preview-actions-json", required=True)
    accept.add_argument("--max-nodes", type=int, default=256)
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_acceptance_demo()
        elif args.command == "accept":
            result = accept_control(
                _parse_json(args.source_json, "control source"),
                args.team,
                _parse_json(args.operations_json, "control edits"),
                _parse_json(args.preview_actions_json, "preview actions"),
                max_nodes=args.max_nodes,
            )
        else:
            result = verify_acceptance(
                _parse_json(args.receipt_json, "acceptance receipt"),
            )
        print(_encoded(result))
        return 0 if result["status"] == "passed_offline_gameplay_witness" else 3
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
