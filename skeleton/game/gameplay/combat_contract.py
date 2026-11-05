"""Replay-verified, original combat mission contracts and earned rewards.

An authored contract wraps canonical turn combat; neither an action nor an
imported checkpoint can claim rewards. The only authority for a result is
replaying the bounded combat journal against its validated source. Hashes
detect corruption and are not authentication signatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
    normalize_scenario, new_session, original_demo, resume_session,
    verify_session, _advance as advance_combat,
)

SCHEMA = "skeleton.combat_contract.v1"
BUNDLE_SCHEMA = "skeleton.combat_contract_bundle.v1"
MAX_OBJECTIVES = 12
MAX_SOURCE_BYTES = 128 * 1024
MAX_SESSION_BYTES = 2 * 1024 * 1024


def _bounded(value: Any, maximum: int) -> None:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("combat contract is not canonical JSON") from exc
    if len(raw) > maximum:
        raise CombatSessionError("combat contract byte budget exceeded")


def normalize_contract(raw: Any) -> dict[str, Any]:
    """Reject unknown source fields and references before playing any turns."""
    _bounded(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {"schema_version", "contract_id", "scenario",
                        "player_team", "objectives", "reward"}, "combat contract")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported combat contract schema")
    scenario = normalize_scenario(obj["scenario"])
    player_team = _id(obj["player_team"], "player_team")
    actors = {actor["id"]: actor for actor in scenario["actors"]}
    if player_team not in {actor["team"] for actor in actors.values()}:
        raise CombatSessionError("player team missing from scenario")
    objectives = obj["objectives"]
    if type(objectives) is not list or not 1 <= len(objectives) <= MAX_OBJECTIVES:
        raise CombatSessionError("invalid objective count")
    normalized = []
    ids: set[str] = set()
    for raw_objective in objectives:
        if type(raw_objective) is not dict:
            raise CombatSessionError("invalid objective")
        kind = raw_objective.get("kind")
        if kind == "defeat":
            entry = _object(raw_objective, {"id", "kind", "actor_id"}, "defeat objective")
            actor_id = _id(entry["actor_id"], "objective actor")
            if actor_id not in actors or actors[actor_id]["team"] == player_team:
                raise CombatSessionError("defeat objective must target an opponent")
            objective = {"id": _id(entry["id"], "objective id"),
                         "kind": kind, "actor_id": actor_id}
        elif kind == "guard":
            entry = _object(raw_objective, {"id", "kind", "minimum"},
                            "guard objective")
            objective = {"id": _id(entry["id"], "objective id"),
                         "kind": kind,
                         "minimum": _integer(entry["minimum"], "minimum", 1, 64)}
        elif kind == "speed":
            entry = _object(raw_objective, {"id", "kind", "maximum_turns"},
                            "speed objective")
            objective = {"id": _id(entry["id"], "objective id"),
                         "kind": kind,
                         "maximum_turns": _integer(
                             entry["maximum_turns"], "maximum_turns",
                             1, scenario["turn_limit"])}
        else:
            raise CombatSessionError("unsupported contract objective kind")
        if objective["id"] in ids:
            raise CombatSessionError("duplicate objective id")
        ids.add(objective["id"])
        normalized.append(objective)
    normalized.sort(key=lambda x: x["id"])
    reward = _object(obj["reward"], {"credits", "item_id"}, "contract reward")
    return {
        "schema_version": SCHEMA,
        "contract_id": _id(obj["contract_id"], "contract_id"),
        "scenario": scenario,
        "player_team": player_team,
        "objectives": normalized,
        "reward": {
            "credits": _integer(reward["credits"], "reward credits", 0, 10000),
            "item_id": _id(reward["item_id"], "reward item_id"),
        },
    }


def _progress(source: dict[str, Any], combat: dict[str, Any]) -> dict[str, bool]:
    state = combat["state"]
    team_by_id = {a["id"]: a["team"] for a in source["scenario"]["actors"]}
    guards = sum(
        event["action"]["kind"] == "guard"
        and team_by_id[event["action"]["actor_id"]] == source["player_team"]
        for event in combat["journal"]
    )
    progress: dict[str, bool] = {}
    for objective in source["objectives"]:
        kind = objective["kind"]
        if kind == "defeat":
            earned = state["actors"][objective["actor_id"]]["hp"] == 0
        elif kind == "guard":
            earned = guards >= objective["minimum"]
        else:
            earned = (state["phase"] == "won"
                      and state["winner"] == source["player_team"]
                      and state["tick"] <= objective["maximum_turns"])
        progress[objective["id"]] = earned
    return progress


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["scenario"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _event_bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "combat.contract.action",
                      event["action"]["actor_id"], event["receipt"])
        for i, event in enumerate(journal)
    )).digest


def new_contract(raw: Any) -> dict[str, Any]:
    source = normalize_contract(raw)
    combat = new_session(source["scenario"])
    state = {
        "tick": 0, "phase": "active", "combat": combat,
        "objectives": _progress(source, combat),
        "credits": 0, "inventory": {}, "winner": None,
    }
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(source, state),
    }


def _advance(session: dict[str, Any], action: Any) -> dict[str, Any]:
    source, previous = session["source"], session["state"]
    if previous["phase"] != "active":
        raise CombatSessionError("contract is already terminal")
    # Only called with canonical sessions from new_contract or verified replay.
    # Avoid quadratic nested verification on every internal simulation step.
    combat = advance_combat(previous["combat"], action)
    progress = _progress(source, combat)
    combat_phase = combat["state"]["phase"]
    phase = "active"
    if combat_phase != "active":
        if combat_phase == "won" and combat["state"]["winner"] == source["player_team"]:
            phase = "won" if all(progress.values()) else "failed"
        else:
            phase = "draw" if combat_phase == "draw" else "lost"
    state = {
        "tick": previous["tick"] + 1, "phase": phase, "combat": combat,
        "objectives": progress,
        "credits": source["reward"]["credits"] if phase == "won" else 0,
        "inventory": {source["reward"]["item_id"]: 1} if phase == "won" else {},
        "winner": combat["state"]["winner"] if combat_phase == "won" else None,
    }
    normalized_action = combat["journal"][-1]["action"]
    event = {
        "sequence": previous["tick"], "action": normalized_action,
        "before": session["state_digest"], "after": dig(state),
        "combat_receipt": combat["journal"][-1]["receipt"],
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _event_bus(journal),
        "save": _save(source, state, session["save"]),
    }
    _bounded(result, MAX_SESSION_BYTES)
    return result


def verify_contract(raw: Any) -> dict[str, Any]:
    """Reconstruct every nested combat action, objective, reward and save."""
    _bounded(raw, MAX_SESSION_BYTES)
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "contract session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported contract session schema")
    replayed = new_contract(obj["source"])
    journal = obj["journal"]
    if (type(journal) is not list
            or len(journal) > replayed["source"]["scenario"]["turn_limit"]):
        raise CombatSessionError("invalid contract journal budget")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("malformed contract event")
        replayed = _advance(replayed, event["action"])
        if replayed["journal"][-1] != event:
            raise CombatSessionError("contract event replay mismatch")
    if replayed != obj:
        raise CombatSessionError("contract state, reward or save mismatch")
    return replayed


def resume_contract(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_contract(raw)
    if (type(actions) is not list
            or len(actions) + len(session["journal"])
            > session["source"]["scenario"]["turn_limit"]):
        raise CombatSessionError("invalid contract action batch")
    _bounded(actions, MAX_SOURCE_BYTES)
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_contract(source: Any, actions: Any) -> dict[str, Any]:
    return resume_contract(new_contract(source), actions)


def export_contract(raw: Any) -> dict[str, Any]:
    session = verify_contract(raw)
    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle, MAX_SESSION_BYTES)
    return bundle


def import_contract(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_SESSION_BYTES)
    obj = _object(raw, {
        "schema_version", "source_digest", "state_digest",
        "session", "checksum",
    }, "contract bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA:
        raise CombatSessionError("unsupported contract bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("contract bundle checksum mismatch")
    session = verify_contract(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise CombatSessionError("contract bundle source/state mismatch")
    return session


def original_contract() -> dict[str, Any]:
    scenario, _ = original_demo()
    return {
        "schema_version": SCHEMA, "contract_id": "bridge_watch_clearance",
        "scenario": scenario, "player_team": "wayfarers",
        "objectives": [
            {"id": "defeat_warden", "kind": "defeat", "actor_id": "warden"},
            {"id": "swift_resolution", "kind": "speed", "maximum_turns": 4},
        ],
        "reward": {"credits": 14, "item_id": "bridge_pass"},
    }


def demo_contract() -> dict[str, Any]:
    _, actions = original_demo()
    return simulate_contract(original_contract(), actions)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-contract")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command, flags in {
        "simulate": ("source-json", "actions-json"),
        "resume": ("session-json", "actions-json"),
        "verify": ("session-json",),
        "export": ("session-json",),
        "import": ("bundle-json",),
    }.items():
        p = sub.add_parser(command)
        for flag in flags:
            p.add_argument("--" + flag, required=True)
    args = parser.parse_args(list(argv))
    try:
        def read(name: str) -> Any:
            return _parse_json(getattr(args, name.replace("-", "_")), name)
        if args.command == "demo":
            result = demo_contract()
        elif args.command == "simulate":
            result = simulate_contract(read("source-json"), read("actions-json"))
        elif args.command == "resume":
            result = resume_contract(read("session-json"), read("actions-json"))
        elif args.command == "verify":
            result = verify_contract(read("session-json"))
        elif args.command == "export":
            result = export_contract(read("session-json"))
        else:
            result = import_contract(read("bundle-json"))
        _bounded(result, MAX_SESSION_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            RecursionError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
