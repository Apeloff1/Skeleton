"""Multi-arena control-point campaign with earned rewards and durable replay.

Each round is a complete canonical control-point match. Rewards are credited
only from independently replayed terminal wins by the authored player team;
no imported scoreboard, reward, or save digest is trusted.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import (
    _encoded, normalize_control, original_actions, original_control,
    play_control, verify_control,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import (
    SaveableGameplayState, dig,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_campaign.v1"
PACKAGE_SCHEMA = "skeleton.arena_control_campaign_package.v1"
MAX_STAGES = 4
MAX_CURRENCY = 100000


def normalize_campaign(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "campaign_id", "world_id",
        "player_team", "required_wins", "stages",
    }, "control-point campaign")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point campaign schema")
    campaign_id = _id(obj["campaign_id"], "campaign_id")
    world_id = _id(obj["world_id"], "world_id")
    team = _id(obj["player_team"], "player_team")
    stages_raw = obj["stages"]
    if type(stages_raw) is not list or not 1 <= len(stages_raw) <= MAX_STAGES:
        raise CombatSessionError("invalid control-point campaign stage count")
    required = _integer(obj["required_wins"], "required_wins", 1, len(stages_raw))
    stages: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in stages_raw:
        entry = _object(item, {"control", "reward"}, "control-point campaign stage")
        control = normalize_control(entry["control"])
        if control["arena"]["world_id"] != world_id:
            raise CombatSessionError("control-point campaign world mismatch")
        if control["control_id"] in ids:
            raise CombatSessionError("duplicate control-point campaign stage")
        ids.add(control["control_id"])
        teams = {a["team"] for a in control["arena"]["actors"]}
        if team not in teams:
            raise CombatSessionError("campaign player team absent from stage")
        reward = _integer(entry["reward"], "reward", 0, MAX_CURRENCY)
        stages.append({"control": control, "reward": reward})
    if sum(stage["reward"] for stage in stages) > MAX_CURRENCY:
        raise CombatSessionError("control-point campaign reward budget exceeded")
    source = {
        "schema_version": SCHEMA, "campaign_id": campaign_id,
        "world_id": world_id, "player_team": team,
        "required_wins": required, "stages": stages,
    }
    _encoded(source)
    return source


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1,
        tick=sum(stage["tick"] for stage in state["rounds"]),
        state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_campaign(raw: Any) -> dict[str, Any]:
    source = normalize_campaign(raw)
    state = {
        "next_index": 0, "wins": 0, "losses": 0, "draws": 0,
        "currency": 0, "phase": "active", "rounds": [],
    }
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "state": state,
        "state_digest": dig(state), "journal": [],
        "save": _save(source, state),
    }


def _advance(snapshot: dict[str, Any], raw_actions: Any) -> dict[str, Any]:
    source, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active":
        raise CombatSessionError("control-point campaign is terminal")
    index = old["next_index"]
    if not 0 <= index < len(source["stages"]):
        raise CombatSessionError("control-point campaign stage index invalid")
    stage = source["stages"][index]
    if type(raw_actions) is not list or not 1 <= len(raw_actions) <= stage["control"]["max_actions"]:
        raise CombatSessionError("invalid control-point campaign action batch")
    played = play_control(stage["control"], raw_actions)
    if played["state"]["phase"] == "active":
        raise CombatSessionError("control-point campaign stage must finish before settlement")
    won = played["state"]["phase"] == "won" and played["state"]["winner"] == source["player_team"]
    draw = played["state"]["phase"] == "draw"
    reward = stage["reward"] if won else 0
    currency = old["currency"] + reward
    if currency > MAX_CURRENCY:
        raise CombatSessionError("control-point campaign currency overflow")
    state = {
        "next_index": index + 1,
        "wins": old["wins"] + int(won),
        "losses": old["losses"] + int(not won and not draw),
        "draws": old["draws"] + int(draw),
        "currency": currency,
        "phase": "active",
        "rounds": [*old["rounds"], {
            "control_id": stage["control"]["control_id"],
            "tick": played["state"]["tick"],
            "outcome": "win" if won else "draw" if draw else "loss",
            "reward": reward, "state_digest": played["state_digest"],
        }],
    }
    if state["next_index"] == len(source["stages"]):
        state["phase"] = "won" if state["wins"] >= source["required_wins"] else "lost"
    event = {
        "index": index, "actions": [entry["action"] for entry in played["journal"]],
        "control_session": played, "reward": reward,
        "before": snapshot["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*snapshot["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": snapshot["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": journal, "save": _save(source, state, snapshot["save"]),
    }
    _encoded(result)
    return result


def verify_campaign(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "save",
    }, "control-point campaign checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point campaign checkpoint")
    _encoded(obj)
    rebuilt = new_campaign(obj["source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > len(rebuilt["source"]["stages"]):
        raise CombatSessionError("invalid control-point campaign journal")
    for event in journal:
        if type(event) is not dict or "actions" not in event:
            raise CombatSessionError("invalid control-point campaign event")
        rebuilt = _advance(rebuilt, event["actions"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("control-point campaign event mismatch")
    if rebuilt != obj:
        raise CombatSessionError("control-point campaign replay or save lineage mismatch")
    return rebuilt


def advance_campaign(raw: Any, actions: Any) -> dict[str, Any]:
    return _advance(verify_campaign(raw), actions)


def play_campaign(source: Any, rounds: Any, *, resume: Any = None) -> dict[str, Any]:
    spec = normalize_campaign(source)
    session = new_campaign(spec) if resume is None else verify_campaign(resume)
    if session["source_digest"] != dig(spec):
        raise CombatSessionError("control-point campaign resume source mismatch")
    if type(rounds) is not list or len(rounds) > len(spec["stages"]):
        raise CombatSessionError("invalid control-point campaign round count")
    if len(rounds) + session["state"]["next_index"] > len(spec["stages"]):
        raise CombatSessionError("control-point campaign exceeds stage budget")
    for actions in rounds:
        session = _advance(session, actions)
    return session


def package_campaign(raw: Any) -> dict[str, Any]:
    session = verify_campaign(raw)
    state = session["state"]
    manifest = {
        "campaign_id": session["source"]["campaign_id"],
        "world_id": session["source"]["world_id"],
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
        "next_index": state["next_index"],
        "wins": state["wins"], "losses": state["losses"],
        "draws": state["draws"], "currency": state["currency"],
        "phase": state["phase"],
        "round_digests": [
            event["control_session"]["state_digest"] for event in session["journal"]
        ],
    }
    result = {
        "schema_version": PACKAGE_SCHEMA, "snapshot": session,
        "manifest": manifest, "claim": "integrity_checked_offline_save",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "snapshot", "manifest", "claim", "receipt",
    }, "control-point campaign package")
    if obj["schema_version"] != PACKAGE_SCHEMA or obj["claim"] != "integrity_checked_offline_save":
        raise CombatSessionError("unsupported control-point campaign package")
    _encoded(obj)
    expected = package_campaign(obj["snapshot"])
    if expected != obj:
        raise CombatSessionError("control-point campaign package mismatch")
    return expected


def original_campaign() -> dict[str, Any]:
    first = original_control()
    second = json.loads(_encoded(first))
    second["control_id"] = "lantern_return_beacons"
    second["arena"]["arena_id"] = "canal_return"
    return {
        "schema_version": SCHEMA,
        "campaign_id": "lantern_beacon_patrol",
        "world_id": "lantern_harbor", "player_team": "wayfarers",
        "required_wins": 2,
        "stages": [
            {"control": first, "reward": 10},
            {"control": second, "reward": 20},
        ],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-campaign")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original two-round offline beacon campaign")
    start = sub.add_parser("new")
    start.add_argument("--source-json", required=True)
    play = sub.add_parser("play")
    play.add_argument("--source-json", required=True)
    play.add_argument("--rounds-json", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("--session-json", required=True)
    advance.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = play_campaign(original_campaign(), [original_actions(), original_actions()])
        elif args.command == "new":
            result = new_campaign(_parse_json(args.source_json, "campaign source"))
        elif args.command == "play":
            result = play_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.rounds_json, "campaign rounds"),
            )
        elif args.command == "advance":
            result = advance_campaign(
                _parse_json(args.session_json, "campaign checkpoint"),
                _parse_json(args.actions_json, "stage actions"),
            )
        elif args.command == "verify":
            result = verify_campaign(_parse_json(args.session_json, "campaign checkpoint"))
        elif args.command == "pack":
            result = package_campaign(_parse_json(args.session_json, "campaign checkpoint"))
        else:
            result = verify_package(_parse_json(args.package_json, "campaign package"))
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
