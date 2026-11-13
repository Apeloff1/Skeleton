"""Source-bound NPC faction consequences over canonical playable expedition quests.

Factions are authored policy, not mutable client balances. Every action and
reputation delta is reconstructed from canonical quest replay; a checksum is
corruption evidence, never an authentication or authorization signature.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    MAX_ACTIONS, _advance as advance_quest, demo_actions, new_quest,
    normalize_quest, original_quest,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.quest_factions.v1"
BUNDLE_SCHEMA = "skeleton.quest_factions_bundle.v1"
MAX_FACTIONS = 8
MAX_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 256 * 1024
MAX_STANDING = 96


def _bounded(raw: Any, limit: int) -> None:
    try:
        size = len(json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("faction payload is not canonical JSON") from exc
    if size > limit:
        raise CombatSessionError("faction payload exceeds size budget")


def normalize_factions(raw: Any) -> dict[str, Any]:
    """Validate author references, finite scores, and unique ending policies."""
    _bounded(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {
        "schema_version", "campaign_id", "quest", "factions",
        "ending_requirements",
    }, "faction campaign")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported faction campaign schema")
    campaign_id = _id(obj["campaign_id"], "campaign_id")
    quest = normalize_quest(obj["quest"])
    npc_ids = {npc["id"] for npc in quest["npcs"]}
    factions_raw = obj["factions"]
    if type(factions_raw) is not list or not 1 <= len(factions_raw) <= MAX_FACTIONS:
        raise CombatSessionError("invalid faction count")
    factions = []
    for raw_faction in factions_raw:
        f = _object(raw_faction, {
            "id", "members", "aid_delta", "decline_delta",
        }, "faction")
        members = f["members"]
        if (type(members) is not list or not members or
                len(members) > len(npc_ids)):
            raise CombatSessionError("invalid faction membership")
        members = [_id(member, "faction NPC") for member in members]
        if len(set(members)) != len(members) or not set(members) <= npc_ids:
            raise CombatSessionError("faction references missing or duplicate NPC")
        factions.append({
            "id": _id(f["id"], "faction_id"),
            "members": sorted(members),
            "aid_delta": _integer(f["aid_delta"], "aid_delta", -8, 8),
            "decline_delta": _integer(f["decline_delta"], "decline_delta", -8, 8),
        })
    factions.sort(key=lambda f: f["id"])
    faction_ids = {f["id"] for f in factions}
    if len(faction_ids) != len(factions):
        raise CombatSessionError("duplicate faction id")
    requirements = obj["ending_requirements"]
    if type(requirements) is not list or len(requirements) > len(quest["endings"]):
        raise CombatSessionError("invalid faction ending requirements")
    ending_ids = {ending["id"] for ending in quest["endings"]}
    normalized_requirements = []
    for raw_requirement in requirements:
        rule = _object(raw_requirement, {
            "ending_id", "minimum_standing",
        }, "faction ending requirement")
        ending_id = _id(rule["ending_id"], "ending_id")
        if ending_id not in ending_ids:
            raise CombatSessionError("faction requirement references unknown ending")
        limits = rule["minimum_standing"]
        if type(limits) is not list or len(limits) > len(factions):
            raise CombatSessionError("invalid minimum standing list")
        normalized_limits = []
        for raw_limit in limits:
            limit = _object(raw_limit, {"faction_id", "minimum"}, "standing")
            faction_id = _id(limit["faction_id"], "faction_id")
            if faction_id not in faction_ids:
                raise CombatSessionError("unknown faction requirement")
            normalized_limits.append({
                "faction_id": faction_id,
                "minimum": _integer(limit["minimum"], "minimum", -MAX_STANDING, MAX_STANDING),
            })
        normalized_limits.sort(key=lambda limit: limit["faction_id"])
        if len({limit["faction_id"] for limit in normalized_limits}) != len(normalized_limits):
            raise CombatSessionError("duplicate faction standing requirement")
        normalized_requirements.append({
            "ending_id": ending_id, "minimum_standing": normalized_limits,
        })
    normalized_requirements.sort(key=lambda rule: rule["ending_id"])
    if len({rule["ending_id"] for rule in normalized_requirements}) != len(normalized_requirements):
        raise CombatSessionError("duplicate faction ending policy")
    return {
        "schema_version": SCHEMA, "campaign_id": campaign_id, "quest": quest,
        "factions": factions, "ending_requirements": normalized_requirements,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["quest"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_factions(source: Any) -> dict[str, Any]:
    spec = normalize_factions(source)
    state = {
        "tick": 0,
        "standing": {f["id"]: 0 for f in spec["factions"]},
        "quest": new_quest(spec["quest"]),
        "phase": "active", "ending": None,
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(spec, state),
    }


def _event_digest(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "factions.action", event["action"]["kind"], event["receipt"])
        for i, event in enumerate(journal)
    )).digest


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise CombatSessionError("faction campaign already terminal")
    if old["tick"] >= MAX_ACTIONS:
        raise CombatSessionError("faction campaign action budget exhausted")
    # The canonical quest engine normalizes and authorizes every action.
    # A rejected action does not mutate the prior session.
    quest = advance_quest(old["quest"], raw)
    action = quest["journal"][-1]["action"]
    standing = dict(old["standing"])
    if action["kind"] == "talk":
        for faction in source["factions"]:
            if action["npc_id"] in faction["members"]:
                delta = faction[
                    "aid_delta" if action["decision"] == "aid" else "decline_delta"
                ]
                standing[faction["id"]] += delta
                if abs(standing[faction["id"]]) > MAX_STANDING:
                    raise CombatSessionError("faction standing budget exceeded")
    if action["kind"] == "finish":
        for rule in source["ending_requirements"]:
            if rule["ending_id"] == action["ending_id"]:
                for limit in rule["minimum_standing"]:
                    if standing[limit["faction_id"]] < limit["minimum"]:
                        raise CombatSessionError("faction standing ending not earned")
    state = {
        "tick": old["tick"] + 1, "standing": standing, "quest": quest,
        "phase": "finished" if quest["state"]["phase"] == "finished" else "active",
        "ending": quest["state"]["ending"],
    }
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
        "quest_receipt": quest["journal"][-1]["receipt"],
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _event_digest(journal),
        "save": _save(source, state, session["save"]),
    }
    _bounded(result, MAX_BYTES)
    return result


def verify_factions(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "faction session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported faction session schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise CombatSessionError("invalid faction journal")
    rebuilt = new_factions(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid faction journal event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("faction event receipt mismatch")
    if rebuilt != obj:
        raise CombatSessionError("faction replay or save mismatch")
    return rebuilt


def resume_factions(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_factions(raw)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise CombatSessionError("invalid faction action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_factions(source: Any, actions: Any) -> dict[str, Any]:
    return resume_factions(new_factions(source), actions)


def export_factions(raw: Any) -> dict[str, Any]:
    session = verify_factions(raw)
    bundle = {
        "schema_version": BUNDLE_SCHEMA, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle, MAX_BYTES)
    return bundle


def import_factions(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    obj = _object(raw, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "faction bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA:
        raise CombatSessionError("unsupported faction bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("faction bundle checksum mismatch")
    session = verify_factions(obj["session"])
    if (session["source_digest"] != obj["source_digest"] or
            session["state_digest"] != obj["state_digest"]):
        raise CombatSessionError("faction bundle source/state mismatch")
    return session


def compare_factions(left: Any, right: Any) -> dict[str, Any]:
    lhs, rhs = verify_factions(left), verify_factions(right)
    if lhs["source_digest"] != rhs["source_digest"]:
        raise CombatSessionError("cannot compare different faction sources")
    common = 0
    for a, b in zip(lhs["journal"], rhs["journal"]):
        if a["receipt"] != b["receipt"]:
            break
        common += 1
    result = {
        "schema_version": "skeleton.quest_factions_compare.v1",
        "source_digest": lhs["source_digest"], "common_action_prefix": common,
        "left": {
            "state_digest": lhs["state_digest"],
            "standing": lhs["state"]["standing"], "ending": lhs["state"]["ending"],
        },
        "right": {
            "state_digest": rhs["state_digest"],
            "standing": rhs["state"]["standing"], "ending": rhs["state"]["ending"],
        },
    }
    result["checksum"] = dig(result)
    return result


def original_factions() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "campaign_id": "lantern_accord",
        "quest": original_quest(),
        "factions": [{
            "id": "harbor_wardens", "members": ["guide", "smith"],
            "aid_delta": 2, "decline_delta": -1,
        }],
        "ending_requirements": [{
            "ending_id": "beacon_lit",
            "minimum_standing": [{"faction_id": "harbor_wardens", "minimum": 4}],
        }],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-factions")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name, flags in {
        "simulate": ("source-json", "actions-json"),
        "resume": ("session-json", "actions-json"),
        "verify": ("session-json",),
        "export": ("session-json",),
        "import": ("bundle-json",),
        "compare": ("left-json", "right-json"),
    }.items():
        p = sub.add_parser(name)
        for flag in flags:
            p.add_argument("--" + flag, required=True)
    args = parser.parse_args(list(argv))
    try:
        def read(flag: str) -> Any:
            return _parse_json(getattr(args, flag.replace("-", "_")), flag)
        if args.command == "demo":
            result = simulate_factions(original_factions(), demo_actions())
        elif args.command == "simulate":
            result = simulate_factions(read("source-json"), read("actions-json"))
        elif args.command == "resume":
            result = resume_factions(read("session-json"), read("actions-json"))
        elif args.command == "verify":
            result = verify_factions(read("session-json"))
        elif args.command == "export":
            result = export_factions(read("session-json"))
        elif args.command == "import":
            result = import_factions(read("bundle-json"))
        else:
            result = compare_factions(read("left-json"), read("right-json"))
        _bounded(result, MAX_BYTES)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("faction CLI output exceeds size budget")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
