"""Cooperative source-bound market campaign with role-gated turns and replay.

This is a turn arbitration layer, not a second economy. Every trade, craft,
delivery, collision and pickup is executed by the canonical market reducer.
Party passes never mint credits or change the underlying market state.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _advance as advance_market, _json, new_market, normalize_market,
    original_market, verify_market,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS, _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_party.v1"
BUNDLE = "skeleton.scene_market_party_bundle.v1"
ROLES = {"navigator": "tile", "merchant": "buy",
         "artisan": "craft", "courier": "deliver"}
MAX_PLAYERS = 4


def normalize_party(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "market_source", "players"},
                  "market party source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported market party source")
    market_source = normalize_market(obj["market_source"])
    players = obj["players"]
    if type(players) is not list or not 2 <= len(players) <= MAX_PLAYERS:
        raise SceneTravelError("party requires two to four players")
    cleaned = []
    for item in players:
        player = _object(item, {"player_id", "roles"}, "party player")
        player_id = _id(player["player_id"], "player id")
        roles = player["roles"]
        if (type(roles) is not list or not 1 <= len(roles) <= len(ROLES)
                or any(type(role) is not str or role not in ROLES for role in roles)
                or len(set(roles)) != len(roles)):
            raise SceneTravelError("invalid party player roles")
        cleaned.append({"player_id": player_id, "roles": sorted(roles)})
    if len({p["player_id"] for p in cleaned}) != len(cleaned):
        raise SceneTravelError("duplicate party player")
    if set().union(*(set(p["roles"]) for p in cleaned)) != set(ROLES):
        raise SceneTravelError("party has uncovered production role")
    return {"schema_version": SCHEMA, "market_source": market_source,
            "players": cleaned}


def _save(source: dict[str, Any], state: dict[str, Any],
          previous: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"source_digest": dig(source), "state_digest": dig(state),
            "sequence": state["sequence"],
            "parent_save_digest": dig(previous) if previous is not None else None}


def new_party(raw: Any) -> dict[str, Any]:
    source = normalize_party(raw)
    market = new_market(source["market_source"])
    state = {"sequence": 0, "turn_index": 0, "round": 0,
             "market": market,
             "contributions": {p["player_id"]: {k: 0 for k in ROLES}
                               for p in source["players"]},
             "passes": {p["player_id"]: 0 for p in source["players"]}}
    return {"schema_version": SCHEMA, "source": source,
            "source_digest": dig(source), "state": state,
            "state_digest": dig(state), "journal": [],
            "save": _save(source, state)}


def _party_action(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"player_id", "action"}, "party turn")
    actor = _id(obj["player_id"], "turn actor")
    action = obj["action"]
    if type(action) is not dict or type(action.get("kind")) is not str:
        raise SceneTravelError("invalid party action")
    if action["kind"] == "pass":
        _object(action, {"kind"}, "party pass")
        return {"player_id": actor, "action": {"kind": "pass"}}
    # The nested canonical reducer validates every economy action and tile field.
    if action["kind"] not in ROLES.values():
        raise SceneTravelError("unsupported party action")
    return {"player_id": actor, "action": copy.deepcopy(action)}


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if (old["market"]["state"]["phase"] != "active"
            or old["sequence"] >= MAX_STEPS):
        raise SceneTravelError("party terminal or action budget exhausted")
    turn = _party_action(raw)
    player = source["players"][old["turn_index"]]
    if turn["player_id"] != player["player_id"]:
        raise SceneTravelError("not this player's turn")
    kind = turn["action"]["kind"]
    required_role = next((role for role, action in ROLES.items()
                          if action == kind), None)
    if required_role is not None and required_role not in player["roles"]:
        raise SceneTravelError("player lacks role for canonical action")
    # No mutable references escape; canonical market reducer is transactional.
    market = (old["market"] if kind == "pass"
              else advance_market(old["market"], turn["action"]))
    contributions = {pid: dict(value)
                     for pid, value in old["contributions"].items()}
    passes = dict(old["passes"])
    if kind == "pass":
        passes[player["player_id"]] += 1
    else:
        contributions[player["player_id"]][required_role] += 1
    next_index = (old["turn_index"] + 1) % len(source["players"])
    state = {"sequence": old["sequence"] + 1, "turn_index": next_index,
             "round": old["round"] + (1 if next_index == 0 else 0),
             "market": market, "contributions": contributions, "passes": passes}
    event = {"sequence": old["sequence"], "turn": turn,
             "before": session["state_digest"], "after": dig(state),
             "market_before": old["market"]["state_digest"],
             "market_after": market["state_digest"]}
    event["receipt"] = dig(event)
    result = {"schema_version": SCHEMA, "source": source,
              "source_digest": session["source_digest"],
              "state": state, "state_digest": dig(state),
              "journal": [*session["journal"], event],
              "save": _save(source, state, session["save"])}
    _bounded(result)
    return result


def verify_party(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source", "source_digest",
                        "state", "state_digest", "journal", "save"},
                  "party checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported party checkpoint")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid party replay length")
    rebuilt = new_party(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "turn" not in event:
            raise SceneTravelError("invalid party event")
        rebuilt = _advance(rebuilt, event["turn"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("party event receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("party checkpoint lineage mismatch")
    if verify_market(rebuilt["state"]["market"]) != rebuilt["state"]["market"]:
        raise SceneTravelError("nested market replay mismatch")
    return rebuilt


def resume_party(checkpoint: Any, turns: Any) -> dict[str, Any]:
    session = verify_party(checkpoint)
    if (type(turns) is not list
            or len(turns) + len(session["journal"]) > MAX_STEPS):
        raise SceneTravelError("invalid party turn batch")
    for turn in turns:
        session = _advance(session, turn)
    return session


def simulate_party(source: Any, turns: Any) -> dict[str, Any]:
    return resume_party(new_party(source), turns)


def export_party(checkpoint: Any) -> dict[str, Any]:
    session = verify_party(checkpoint)
    bundle = {"schema_version": BUNDLE, "session": session,
              "source_digest": session["source_digest"],
              "state_digest": session["state_digest"]}
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_party(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    bundle = _object(raw, {"schema_version", "session", "source_digest",
                           "state_digest", "checksum"}, "party export")
    if bundle["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported party export")
    if bundle["checksum"] != dig({k: v for k, v in bundle.items()
                                  if k != "checksum"}):
        raise SceneTravelError("party export checksum mismatch")
    session = verify_party(bundle["session"])
    if (session["source_digest"] != bundle["source_digest"]
            or session["state_digest"] != bundle["state_digest"]):
        raise SceneTravelError("party export source/state mismatch")
    return session


def original_party() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    market, actions = original_market()
    source = {"schema_version": SCHEMA, "market_source": market,
              "players": [
                  {"player_id": "rowan", "roles": ["navigator", "merchant"]},
                  {"player_id": "mira", "roles": ["navigator", "artisan"]},
                  {"player_id": "tavi", "roles": ["navigator", "courier"]},
              ]}
    roles = {p["player_id"]: set(p["roles"]) for p in source["players"]}
    turns = []
    for action in actions:
        required = next(k for k, v in ROLES.items() if v == action["kind"])
        while required not in roles[source["players"][len(turns) % 3]["player_id"]]:
            actor = source["players"][len(turns) % 3]["player_id"]
            turns.append({"player_id": actor, "action": {"kind": "pass"}})
        actor = source["players"][len(turns) % 3]["player_id"]
        turns.append({"player_id": actor, "action": action})
    return source, turns


def accept_party(source: Any, turns: Any) -> dict[str, Any]:
    if type(turns) is not list:
        raise SceneTravelError("invalid party acceptance turns")
    middle = len(turns) // 2
    before = simulate_party(source, turns[:middle])
    final = resume_party(import_party(export_party(before)), turns[middle:])
    direct = simulate_party(source, turns)
    if final != direct or final["state"]["market"]["state"]["phase"] != "won":
        raise SceneTravelError("party acceptance did not finish or replay")
    bundle = export_party(final)
    if import_party(bundle) != final:
        raise SceneTravelError("party acceptance export did not replay")
    return {"schema_version": "skeleton.scene_market_party_acceptance.v1",
            "source_digest": final["source_digest"],
            "state_digest": final["state_digest"],
            "market_state_digest": final["state"]["market"]["state_digest"],
            "turns": len(turns), "phase": "won",
            "contributions": final["state"]["contributions"],
            "passes": final["state"]["passes"],
            "export_checksum": bundle["checksum"]}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("accept")
    for command in ("simulate", "resume"):
        p = sub.add_parser(command)
        p.add_argument("--source-json" if command == "simulate"
                       else "--session-json", required=True)
        p.add_argument("--turns-json", required=True)
    for command in ("verify", "export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command in ("demo", "accept"):
            source, turns = original_party()
            result = (simulate_party(source, turns) if args.command == "demo"
                      else accept_party(source, turns))
        elif args.command == "simulate":
            result = simulate_party(_json(args.source_json), _json(args.turns_json))
        elif args.command == "resume":
            result = resume_party(_json(args.session_json), _json(args.turns_json))
        elif args.command in ("verify", "export"):
            session = _json(args.session_json)
            result = (verify_party(session) if args.command == "verify"
                      else export_party(session))
        else:
            result = import_party(_json(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
