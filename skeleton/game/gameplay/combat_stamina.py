"""Replay-verified tactical stamina over canonical authored turn combat."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import EventBus, GameplayEvent, SaveableGameplayState, dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_TURNS, _action, _active_actor, _advance as advance_combat,
    _id, _integer, _object, _parse_json, new_session, normalize_scenario, original_demo,
)

SCHEMA = "skeleton.combat_stamina.v1"
BUNDLE = "skeleton.combat_stamina_bundle.v1"
MAX_BYTES = 2 * 1024 * 1024


def _bounded(raw: Any) -> None:
    try:
        size = len(json.dumps(raw, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid stamina JSON") from exc
    if size > MAX_BYTES:
        raise CombatSessionError("stamina byte budget exceeded")


def normalize_stamina(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "scenario", "player_team",
                        "max_stamina", "attack_cost", "guard_cost", "rest_gain"}, "stamina source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported stamina schema")
    scenario = normalize_scenario(obj["scenario"])
    team = _id(obj["player_team"], "player team")
    if team not in {a["team"] for a in scenario["actors"]}:
        raise CombatSessionError("stamina player team absent")
    maximum = _integer(obj["max_stamina"], "max stamina", 1, 32)
    return {"schema_version": SCHEMA, "scenario": scenario, "player_team": team,
            "max_stamina": maximum,
            "attack_cost": _integer(obj["attack_cost"], "attack cost", 1, maximum),
            "guard_cost": _integer(obj["guard_cost"], "guard cost", 0, maximum),
            "rest_gain": _integer(obj["rest_gain"], "rest gain", 1, maximum)}


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["scenario"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_stamina(raw: Any) -> dict[str, Any]:
    source = normalize_stamina(raw)
    combat = new_session(source["scenario"])
    state = {"tick": 0, "combat": combat, "phase": combat["state"]["phase"],
             "winner": combat["state"]["winner"],
             "stamina": {a["id"]: source["max_stamina"] for a in source["scenario"]["actors"]}}
    return {"schema_version": SCHEMA, "source": source, "source_digest": dig(source),
            "state": state, "state_digest": dig(state), "journal": [],
            "event_bus_digest": EventBus().digest, "save": _save(source, state)}


def _step(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old, source = session["state"], session["source"]
    if old["phase"] != "active":
        raise CombatSessionError("stamina combat already terminal")
    action = _action(raw)
    actor, _ = _active_actor(source["scenario"], old["combat"]["state"])
    if actor != action["actor_id"]:
        raise CombatSessionError("stamina action out of turn")
    energy = dict(old["stamina"])
    if action["kind"] in ("attack", "guard"):
        cost = source["attack_cost" if action["kind"] == "attack" else "guard_cost"]
        if energy[actor] < cost:
            raise CombatSessionError("insufficient stamina")
        energy[actor] -= cost
    else:
        energy[actor] = min(source["max_stamina"], energy[actor] + source["rest_gain"])
    combat = advance_combat(old["combat"], action)
    state = {"tick": old["tick"] + 1, "combat": combat,
             "phase": combat["state"]["phase"], "winner": combat["state"]["winner"],
             "stamina": energy}
    event = {"sequence": old["tick"], "action": action,
             "before": session["state_digest"], "after": dig(state),
             "combat_receipt": combat["journal"][-1]["receipt"]}
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    bus = EventBus(tuple(
        GameplayEvent(i, "combat.stamina", e["action"]["actor_id"], e["receipt"])
        for i, e in enumerate(journal)
    )).digest
    result = {"schema_version": SCHEMA, "source": source,
              "source_digest": session["source_digest"], "state": state,
              "state_digest": dig(state), "journal": journal,
              "event_bus_digest": bus, "save": _save(source, state, session["save"])}
    _bounded(result)
    return result


def verify_stamina(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source", "source_digest", "state",
                        "state_digest", "journal", "event_bus_digest", "save"}, "stamina save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported stamina save")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_TURNS:
        raise CombatSessionError("invalid stamina journal")
    replayed = new_stamina(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid stamina event")
        replayed = _step(replayed, event["action"])
        if replayed["journal"][-1] != event:
            raise CombatSessionError("stamina event replay mismatch")
    if replayed != obj:
        raise CombatSessionError("stamina save or replay mismatch")
    return replayed


def resume_stamina(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_stamina(raw)
    if (type(actions) is not list or len(actions) > MAX_TURNS
            or len(actions) + len(session["journal"]) > session["source"]["scenario"]["turn_limit"]):
        raise CombatSessionError("invalid stamina action batch")
    for action in actions:
        session = _step(session, action)
    return verify_stamina(session)


def simulate_stamina(source: Any, actions: Any) -> dict[str, Any]:
    return resume_stamina(new_stamina(source), actions)


def export_stamina(raw: Any) -> dict[str, Any]:
    session = verify_stamina(raw)
    bundle = {"schema_version": BUNDLE, "kind": "offline_combat_stamina",
              "source_digest": session["source_digest"],
              "state_digest": session["state_digest"], "session": session}
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_stamina(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "kind", "source_digest",
                        "state_digest", "session", "checksum"}, "stamina bundle")
    if obj["schema_version"] != BUNDLE or obj["kind"] != "offline_combat_stamina":
        raise CombatSessionError("unsupported stamina bundle")
    if type(obj["checksum"]) is not str or obj["checksum"] != dig({
        k: v for k, v in obj.items() if k != "checksum"
    }):
        raise CombatSessionError("stamina bundle checksum mismatch")
    session = verify_stamina(obj["session"])
    if obj["source_digest"] != session["source_digest"] or obj["state_digest"] != session["state_digest"]:
        raise CombatSessionError("stamina bundle source mismatch")
    return session


def legal_stamina_actions(raw: Any) -> list[dict[str, str]]:
    session = verify_stamina(raw)
    if session["state"]["phase"] != "active":
        return []
    actor, _ = _active_actor(session["source"]["scenario"], session["state"]["combat"]["state"])
    stats = {a["id"]: a for a in session["source"]["scenario"]["actors"]}
    candidates = [{"kind": "guard", "actor_id": actor},
                  {"kind": "rest", "actor_id": actor}]
    candidates.extend({"kind": "attack", "actor_id": actor, "target_id": target}
                      for target in sorted(stats)
                      if stats[target]["team"] != stats[actor]["team"]
                      and session["state"]["combat"]["state"]["actors"][target]["hp"] > 0)
    legal = []
    for action in candidates:
        try:
            _step(session, action)
        except CombatSessionError:
            continue
        legal.append(action)
    return sorted(legal, key=lambda a: json.dumps(a, sort_keys=True))


def edit_stamina(source: Any, expected_digest: str, edits: Any,
                 preview_actions: Any = None) -> dict[str, Any]:
    spec = normalize_stamina(source)
    if type(expected_digest) is not str or expected_digest != dig(spec):
        raise CombatSessionError("stamina author source digest conflict")
    if type(edits) is not list or len(edits) > 12:
        raise CombatSessionError("invalid stamina edit batch")
    changed = copy.deepcopy(spec)
    for raw in edits:
        edit = _object(raw, {"field", "value"}, "stamina edit")
        if type(edit["field"]) is not str or edit["field"] not in {
            "max_stamina", "attack_cost", "guard_cost", "rest_gain"
        }:
            raise CombatSessionError("unsupported stamina edit")
        changed[edit["field"]] = edit["value"]
    changed = normalize_stamina(changed)
    preview = simulate_stamina(changed, preview_actions) if preview_actions is not None else None
    return {"schema_version": "skeleton.combat_stamina_author.v1",
            "previous_digest": expected_digest, "source_digest": dig(changed),
            "source": changed, "preview": preview}


def original_stamina() -> tuple[dict[str, Any], list[dict[str, str]]]:
    scenario, actions = original_demo()
    return {"schema_version": SCHEMA, "scenario": scenario, "player_team": "wayfarers",
            "max_stamina": 4, "attack_cost": 2, "guard_cost": 1, "rest_gain": 3}, actions


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-stamina")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sim = sub.add_parser("simulate")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for name in ("verify", "export", "legal"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    author = sub.add_parser("author")
    author.add_argument("--source-json", required=True)
    author.add_argument("--expected-digest", required=True)
    author.add_argument("--edits-json", required=True)
    author.add_argument("--preview-actions-json")
    args = parser.parse_args(list(argv))
    try:
        def read(name: str) -> Any:
            return _parse_json(getattr(args, name.replace("-", "_")), name)
        if args.command == "demo":
            source, actions = original_stamina()
            result = simulate_stamina(source, actions)
        elif args.command == "simulate":
            result = simulate_stamina(read("source-json"), read("actions-json"))
        elif args.command == "resume":
            result = resume_stamina(read("session-json"), read("actions-json"))
        elif args.command == "verify":
            result = verify_stamina(read("session-json"))
        elif args.command == "export":
            result = export_stamina(read("session-json"))
        elif args.command == "legal":
            result = legal_stamina_actions(read("session-json"))
        elif args.command == "import":
            result = import_stamina(read("bundle-json"))
        else:
            result = edit_stamina(
                read("source-json"), args.expected_digest, read("edits-json"),
                read("preview-actions-json") if args.preview_actions_json is not None else None,
            )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
