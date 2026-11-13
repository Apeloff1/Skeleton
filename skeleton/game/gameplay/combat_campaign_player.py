"""Human-controlled offline campaign: canonical combat, earned rewards and replay."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import (
    MAX_CURRENCY, normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.tactical_policy import _decide_verified
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _active_actor,
    _advance as advance_combat, _object, _parse_json,
    new_session, verify_session,
)

SCHEMA = "skeleton.combat_campaign_player.v1"
BUNDLE = "skeleton.combat_campaign_player_bundle.v1"
MAX_BYTES = 2 * 1024 * 1024


def _bounded(raw: Any) -> None:
    try:
        size = len(json.dumps(raw, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid playable campaign JSON") from exc
    if size > MAX_BYTES:
        raise CombatSessionError("playable campaign byte budget exceeded")


def _bots(combat: dict[str, Any], hero_team: str) -> dict[str, Any]:
    teams = {actor["id"]: actor["team"] for actor in combat["scenario"]["actors"]}
    while combat["state"]["phase"] == "active":
        actor_id, _ = _active_actor(combat["scenario"], combat["state"])
        if teams[actor_id] == hero_team:
            break
        combat = advance_combat(combat, _decide_verified(combat))
    return combat


def _opening(source: dict[str, Any], index: int, hp: int) -> dict[str, Any]:
    scenario = copy.deepcopy(source["encounters"][index]["scenario"])
    hero = next(a for a in scenario["actors"] if a["id"] == source["hero_id"])
    if not 1 <= hp <= hero["max_hp"]:
        raise CombatSessionError("invalid hero health carryover")
    hero["max_hp"] = hp
    return _bots(new_session(scenario), source["hero_team"])


def _snapshot(source: dict[str, Any], state: dict[str, Any],
              journal: list[dict[str, Any]],
              parent: dict[str, Any] | None = None) -> dict[str, Any]:
    save = {
        "source_digest": dig(source), "state_digest": dig(state),
        "player_turns": state["player_turns"],
        "parent_save_digest": dig(parent) if parent is not None else None,
    }
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "state": state,
        "state_digest": dig(state), "journal": journal, "save": save,
    }
    _bounded(result)
    return result


def new_player_campaign(raw: Any) -> dict[str, Any]:
    source = normalize_campaign(raw)
    hero = next(a for a in source["encounters"][0]["scenario"]["actors"]
                if a["id"] == source["hero_id"])
    combat = _opening(source, 0, hero["max_hp"])
    state = {
        "next_index": 0, "player_turns": 0,
        "hero_hp": combat["state"]["actors"][source["hero_id"]]["hp"],
        "currency": 0,
        "phase": "active" if combat["state"]["phase"] == "active" else "lost",
        "combat": combat, "completed": [],
    }
    return _snapshot(source, state, [])


def _advance(session: dict[str, Any], raw_action: Any) -> dict[str, Any]:
    old, source = session["state"], session["source"]
    if old["phase"] != "active":
        raise CombatSessionError("playable campaign already terminal")
    combat = old["combat"]
    actor_id, _ = _active_actor(combat["scenario"], combat["state"])
    if actor_id != source["hero_id"]:
        raise CombatSessionError("campaign expects player hero turn")
    player_combat = advance_combat(combat, raw_action)
    action = player_combat["journal"][-1]["action"]
    if action["actor_id"] != source["hero_id"]:
        raise CombatSessionError("campaign hero identity mismatch")
    finished = _bots(player_combat, source["hero_team"])
    hp = finished["state"]["actors"][source["hero_id"]]["hp"]
    index, currency = old["next_index"], old["currency"]
    completed = list(old["completed"])
    phase, next_combat = "active", finished
    if finished["state"]["phase"] != "active":
        victory = (finished["state"]["phase"] == "won"
                   and finished["state"]["winner"] == source["hero_team"])
        reward = source["encounters"][index]["reward"] if victory else 0
        currency += reward
        if currency > MAX_CURRENCY:
            raise CombatSessionError("earned currency overflow")
        completed.append({
            "encounter_id": source["encounters"][index]["scenario"]["encounter_id"],
            "reward": reward, "combat": verify_session(finished),
        })
        index += 1
        if not victory:
            phase = "lost" if hp == 0 else "draw"
        elif index == len(source["encounters"]):
            phase = "won"
        else:
            next_combat = _opening(source, index, hp)
            if next_combat["state"]["phase"] != "active":
                hp = next_combat["state"]["actors"][source["hero_id"]]["hp"]
                completed.append({
                    "encounter_id": source["encounters"][index]["scenario"]["encounter_id"],
                    "reward": 0, "combat": verify_session(next_combat),
                })
                index += 1
                phase = "lost" if hp == 0 else "draw"
    state = {
        "next_index": index, "player_turns": old["player_turns"] + 1,
        "hero_hp": hp, "currency": currency, "phase": phase,
        "combat": next_combat, "completed": completed,
    }
    event = {
        "sequence": old["player_turns"], "action": action,
        "before": session["state_digest"], "after": dig(state),
        "combat_receipt": player_combat["journal"][-1]["receipt"],
    }
    event["receipt"] = dig(event)
    return _snapshot(source, state, [*session["journal"], event], session["save"])


def verify_player_campaign(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "save",
    }, "playable campaign save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported playable campaign schema")
    rebuilt = new_player_campaign(obj["source"])
    journal = obj["journal"]
    limit = sum(e["scenario"]["turn_limit"]
                for e in rebuilt["source"]["encounters"])
    if type(journal) is not list or len(journal) > limit:
        raise CombatSessionError("invalid campaign action journal")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid campaign event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("campaign replay receipt mismatch")
    if rebuilt != obj:
        raise CombatSessionError("campaign replay or save lineage mismatch")
    if verify_session(rebuilt["state"]["combat"]) != rebuilt["state"]["combat"]:
        raise CombatSessionError("nested combat replay mismatch")
    return rebuilt


def resume_player_campaign(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_player_campaign(raw)
    if type(actions) is not list or len(actions) > 128:
        raise CombatSessionError("invalid player action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_player_campaign(source: Any, actions: Any) -> dict[str, Any]:
    return resume_player_campaign(new_player_campaign(source), actions)


def export_player_campaign(raw: Any) -> dict[str, Any]:
    session = verify_player_campaign(raw)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_player_campaign(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "playable campaign bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported campaign bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("campaign bundle checksum mismatch")
    session = verify_player_campaign(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise CombatSessionError("campaign bundle lineage mismatch")
    return session


def demo_player_campaign() -> dict[str, Any]:
    current = new_player_campaign(original_campaign())
    while current["state"]["phase"] == "active":
        combat = current["state"]["combat"]
        foes = sorted(a["id"] for a in combat["scenario"]["actors"]
                      if a["team"] != current["source"]["hero_team"]
                      and combat["state"]["actors"][a["id"]]["hp"] > 0)
        if not foes:
            raise CombatSessionError("no live campaign target")
        current = _advance(current, {
            "kind": "attack", "actor_id": current["source"]["hero_id"],
            "target_id": foes[0],
        })
    return verify_player_campaign(current)


def play_player_campaign(source: Any = None, *, session: Any = None,
                         reader: Any = None, writer: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one source or checkpoint")
    current = new_player_campaign(source) if session is None else verify_player_campaign(session)
    input_stream = sys.stdin if reader is None else reader
    output_stream = sys.stdout if writer is None else writer
    while current["state"]["phase"] == "active":
        output_stream.write(json.dumps({
            "event": "hero_turn", "encounter": current["state"]["next_index"],
            "actor_id": current["source"]["hero_id"],
            "state_digest": current["state_digest"],
            "hero_hp": current["state"]["hero_hp"],
            "currency": current["state"]["currency"],
        }, sort_keys=True) + "\n")
        output_stream.flush()
        for attempt in range(3):
            line = input_stream.readline(MAX_CLI_BYTES + 1)
            if not line:
                output_stream.write(json.dumps({
                    "event": "checkpoint", "session": current,
                }) + "\n")
                output_stream.flush()
                raise CombatSessionError("campaign input ended; checkpoint emitted")
            try:
                updated = _advance(current, _parse_json(line, "campaign action"))
            except (CombatSessionError, ValueError, TypeError, KeyError,
                    UnicodeError, RecursionError) as exc:
                output_stream.write(json.dumps({
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": 2 - attempt,
                }) + "\n")
                output_stream.flush()
                if attempt == 2:
                    output_stream.write(json.dumps({
                        "event": "checkpoint", "session": current,
                    }) + "\n")
                    output_stream.flush()
                    raise CombatSessionError("invalid actions; checkpoint emitted") from exc
            else:
                current = updated
                output_stream.write(json.dumps({
                    "event": "checkpoint", "session": current,
                }) + "\n")
                output_stream.flush()
                break
    output_stream.write(json.dumps({
        "event": "terminal", "phase": current["state"]["phase"],
        "currency": current["state"]["currency"],
        "state_digest": current["state_digest"],
    }, sort_keys=True) + "\n")
    output_stream.flush()
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-player")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("simulate", "resume"):
        p = sub.add_parser(command)
        p.add_argument("--source-json" if command == "simulate"
                       else "--session-json", required=True)
        p.add_argument("--actions-json", required=True)
    for command in ("verify", "export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    for name in ("branch-demo", "branch-accept"):
        sub.add_parser(name)
    branch_evaluate = sub.add_parser("branch-evaluate")
    branch_evaluate.add_argument("--session-json", required=True)
    branch_evaluate.add_argument("--candidates-json", required=True)
    for name in ("branch-verify", "branch-export", "branch-choose"):
        branch = sub.add_parser(name)
        branch.add_argument("--report-json", required=True)
        if name == "branch-choose":
            branch.add_argument("--candidate-id", required=True)
    sub.add_parser("branch-import").add_argument("--bundle-json", required=True)
    play = sub.add_parser("play")
    group = play.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_player_campaign()
        elif args.command == "simulate":
            result = simulate_player_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.actions_json, "campaign actions"),
            )
        elif args.command == "resume":
            result = resume_player_campaign(
                _parse_json(args.session_json, "campaign session"),
                _parse_json(args.actions_json, "campaign actions"),
            )
        elif args.command == "verify":
            result = verify_player_campaign(_parse_json(args.session_json, "campaign session"))
        elif args.command == "export":
            result = export_player_campaign(_parse_json(args.session_json, "campaign session"))
        elif args.command == "import":
            result = import_player_campaign(_parse_json(args.bundle_json, "campaign bundle"))
        elif args.command.startswith("branch-"):
            from skeleton.game.gameplay.combat_campaign_branches import (
                accept_branches, choose_branch, demo_branches, evaluate_branches,
                export_branches, import_branches, verify_branches,
            )
            if args.command == "branch-demo":
                result = demo_branches()
            elif args.command == "branch-accept":
                result = accept_branches()
            elif args.command == "branch-evaluate":
                result = evaluate_branches(
                    _parse_json(args.session_json, "campaign checkpoint"),
                    _parse_json(args.candidates_json, "campaign branch plans"))
            elif args.command == "branch-import":
                result = import_branches(_parse_json(args.bundle_json, "branch bundle"))
            else:
                report = _parse_json(args.report_json, "branch report")
                if args.command == "branch-verify":
                    result = verify_branches(report)
                elif args.command == "branch-export":
                    result = export_branches(report)
                else:
                    result = choose_branch(report, args.candidate_id)
        else:
            play_player_campaign(
                _parse_json(args.source_json, "campaign source")
                if args.source_json is not None else None,
                session=(_parse_json(args.session_json, "campaign session")
                         if args.session_json is not None else None),
            )
            return 0
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
