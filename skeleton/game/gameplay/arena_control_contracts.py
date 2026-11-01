"""Source-bound tactical capture contracts, replay, earned rewards and portable saves.

Contract rewards settle once, only after a canonical terminal win. The authored
objectives cannot mutate the arena or manufacture a capture; all evidence is
derived by replaying the canonical arena_control journal.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import (
    _advance_control, _encoded, new_control, normalize_control,
    original_actions, original_control, verify_control,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_contracts.v1"
PACKAGE_SCHEMA = "skeleton.arena_control_contracts_package.v1"
MAX_OBJECTIVES = 12
MAX_REWARD = 100000
MAX_TOTAL_REWARD = 500000


def normalize_contract(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "contract_id", "control",
                        "player_team", "objectives"}, "capture contract source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported capture contract source schema")
    contract_id = _id(obj["contract_id"], "contract_id")
    control = normalize_control(obj["control"])
    team = _id(obj["player_team"], "player_team")
    teams = {actor["team"] for actor in control["arena"]["actors"]}
    if team not in teams:
        raise CombatSessionError("contract player team absent from arena")
    entries = obj["objectives"]
    if type(entries) is not list or not 1 <= len(entries) <= MAX_OBJECTIVES:
        raise CombatSessionError("invalid capture contract objective count")
    objectives = []
    seen = set()
    zone_ids = {zone["id"] for zone in control["zones"]}
    for raw_item in entries:
        item = _object(raw_item, {"id", "kind", "target", "reward"},
                       "capture contract objective")
        objective_id = _id(item["id"], "objective_id")
        if objective_id in seen:
            raise CombatSessionError("duplicate capture contract objective")
        seen.add(objective_id)
        kind = item["kind"]
        if kind == "capture-zone":
            target = _id(item["target"], "zone_id")
            if target not in zone_ids:
                raise CombatSessionError("unknown contract capture zone")
        elif kind == "reach-score":
            target = _integer(item["target"], "score", 1, 1000)
        elif kind == "finish-by":
            target = _integer(item["target"], "turn budget", 1,
                              control["max_actions"])
        elif kind == "survive":
            if item["target"] != "player-team":
                raise CombatSessionError("invalid survival objective target")
            target = "player-team"
        else:
            raise CombatSessionError("unsupported capture contract objective")
        reward = _integer(item["reward"], "contract reward", 0, MAX_REWARD)
        objectives.append({"id": objective_id, "kind": kind,
                           "target": target, "reward": reward})
    if sum(item["reward"] for item in objectives) > MAX_TOTAL_REWARD:
        raise CombatSessionError("capture contract reward budget exceeded")
    source = {"schema_version": SCHEMA, "contract_id": contract_id,
              "control": control, "player_team": team,
              "objectives": sorted(objectives, key=lambda item: item["id"])}
    _encoded(source)
    return source


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["control"]["arena"]["world_id"],
        schema_version=1, tick=state["tick"],
        state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _settlement(source: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    game = control["state"]
    team = source["player_team"]
    terminal = game["phase"] != "active"
    won = game["phase"] == "won" and game["winner"] == team
    actors = control["arena_session"]["state"]["actors"]
    team_ids = {actor["id"] for actor in source["control"]["arena"]["actors"]
                if actor["team"] == team}
    living = any(actors[actor_id]["hp"] > 0 for actor_id in team_ids)
    results = []
    for objective in source["objectives"]:
        kind, target = objective["kind"], objective["target"]
        if kind == "capture-zone":
            achieved = any(c["team"] == team and c["zone_id"] == target
                           for c in game["captures"])
        elif kind == "reach-score":
            achieved = game["scores"][team] >= target
        elif kind == "finish-by":
            achieved = terminal and game["tick"] <= target
        else:
            achieved = terminal and living
        # No reward for a draw, loss or unfinished match.
        earned = objective["reward"] if won and achieved else 0
        results.append({"id": objective["id"], "achieved": bool(achieved),
                        "earned": earned})
    return {"tick": game["tick"], "phase": game["phase"],
            "winner": game["winner"], "settled": terminal,
            "reward": sum(item["earned"] for item in results),
            "objectives": results}


def new_contract(raw: Any) -> dict[str, Any]:
    source = normalize_contract(raw)
    control = new_control(source["control"])
    state = _settlement(source, control)
    return {"schema_version": SCHEMA, "source": source,
            "source_digest": dig(source), "control_session": control,
            "state": state, "state_digest": dig(state),
            "save": _save(source, state)}


def _step(snapshot: dict[str, Any], action: Any) -> dict[str, Any]:
    control = _advance_control(snapshot["control_session"], action)
    state = _settlement(snapshot["source"], control)
    result = {"schema_version": SCHEMA, "source": snapshot["source"],
              "source_digest": snapshot["source_digest"],
              "control_session": control, "state": state,
              "state_digest": dig(state),
              "save": _save(snapshot["source"], state, snapshot["save"])}
    _encoded(result)
    return result


def verify_contract(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "source", "source_digest",
                        "control_session", "state", "state_digest", "save"},
                  "capture contract checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported capture contract checkpoint")
    _encoded(obj)
    source = normalize_contract(obj["source"])
    # Validate the nested replay before extracting untrusted actions.
    control = verify_control(obj["control_session"])
    if control["source_digest"] != dig(source["control"]):
        raise CombatSessionError("capture contract arena source mismatch")
    rebuilt = new_contract(source)
    for event in control["journal"]:
        rebuilt = _step(rebuilt, event["action"])
    if rebuilt != obj:
        raise CombatSessionError("capture contract replay or save lineage mismatch")
    return rebuilt


def resume_contract(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_contract(raw)
    if type(actions) is not list:
        raise CombatSessionError("invalid capture contract action batch")
    if len(actions) + session["state"]["tick"] > session["source"]["control"]["max_actions"]:
        raise CombatSessionError("capture contract action budget exceeded")
    for action in actions:
        session = _step(session, action)
    return session


def play_contract(source: Any, actions: Any) -> dict[str, Any]:
    return resume_contract(new_contract(source), actions)


def package_contract(raw: Any) -> dict[str, Any]:
    session = verify_contract(raw)
    manifest = {"contract_id": session["source"]["contract_id"],
                "world_id": session["source"]["control"]["arena"]["world_id"],
                "source_digest": session["source_digest"],
                "state_digest": session["state_digest"],
                "control_digest": session["control_session"]["state_digest"],
                "save_digest": dig(session["save"]),
                "tick": session["state"]["tick"],
                "phase": session["state"]["phase"],
                "reward": session["state"]["reward"]}
    package = {"schema_version": PACKAGE_SCHEMA, "snapshot": session,
               "manifest": manifest, "claim": "integrity_checked_offline_save"}
    package["receipt"] = dig(package)
    _encoded(package)
    return package


def verify_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "snapshot", "manifest",
                        "claim", "receipt"}, "capture contract package")
    if obj["schema_version"] != PACKAGE_SCHEMA or obj["claim"] != "integrity_checked_offline_save":
        raise CombatSessionError("unsupported capture contract package")
    _encoded(obj)
    expected = package_contract(obj["snapshot"])
    if expected != obj:
        raise CombatSessionError("capture contract package mismatch")
    return expected


def original_contract() -> dict[str, Any]:
    return {"schema_version": SCHEMA, "contract_id": "lantern_beacon_bounty",
            "control": original_control(), "player_team": "wayfarers",
            "objectives": [
                {"id": "secure_west", "kind": "capture-zone",
                 "target": "west_beacon", "reward": 15},
                {"id": "two_points", "kind": "reach-score",
                 "target": 2, "reward": 20},
                {"id": "fast_finish", "kind": "finish-by",
                 "target": 3, "reward": 10},
                {"id": "survivor", "kind": "survive",
                 "target": "player-team", "reward": 5},
            ]}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-contracts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original source-bound beacon bounty")
    start = sub.add_parser("new")
    start.add_argument("--source-json", required=True)
    play = sub.add_parser("play")
    play.add_argument("--source-json", required=True)
    play.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = play_contract(original_contract(), original_actions())
        elif args.command == "new":
            result = new_contract(_parse_json(args.source_json, "contract source"))
        elif args.command == "play":
            result = play_contract(_parse_json(args.source_json, "contract source"),
                                   _parse_json(args.actions_json, "contract actions"))
        elif args.command == "resume":
            result = resume_contract(_parse_json(args.session_json, "contract checkpoint"),
                                     _parse_json(args.actions_json, "contract actions"))
        elif args.command == "verify":
            result = verify_contract(_parse_json(args.session_json, "contract checkpoint"))
        elif args.command == "pack":
            result = package_contract(_parse_json(args.session_json, "contract checkpoint"))
        else:
            result = verify_package(_parse_json(args.package_json, "contract package"))
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
