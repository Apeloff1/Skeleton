"""Offline chapter campaign: authored quests, consequences and replayable delivery.

Campaign progress is reconstructed from chapter actions and authored unlocks.
Checksums are corruption detectors, not signatures or authorization to play
an untrusted source. Consumers must separately establish source provenance.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    MAX_BYTES, MAX_SOURCE_BYTES, _advance as advance_quest,
    _size, demo_actions, new_quest, normalize_quest, original_quest,
    verify_quest,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _object, _parse_json,
)

SCHEMA = "skeleton.quest_chapter_campaign.v1"
BUNDLE_SCHEMA = "skeleton.quest_chapter_campaign_bundle.v1"
MAX_CHAPTERS = 4
MAX_ACTIONS = 96
MAX_FLAGS = 24


def _ids(raw: Any, label: str) -> list[str]:
    if type(raw) is not list or len(raw) > MAX_FLAGS:
        raise CombatSessionError(f"invalid {label} list")
    names = [_id(value, label) for value in raw]
    if len(set(names)) != len(names):
        raise CombatSessionError(f"duplicate {label}")
    return sorted(names)


def normalize_campaign(raw: Any) -> dict[str, Any]:
    """Validate all chapter sources and consequence references before play."""
    _size(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {"schema_version", "world_id", "campaign_id",
                        "chapters"}, "chapter campaign")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported chapter campaign schema")
    world_id = _id(obj["world_id"], "world_id")
    campaign_id = _id(obj["campaign_id"], "campaign_id")
    chapters = obj["chapters"]
    if type(chapters) is not list or not 1 <= len(chapters) <= MAX_CHAPTERS:
        raise CombatSessionError("invalid campaign chapter count")
    seen_chapters: set[str] = set()
    seen_quests: set[str] = set()
    available_flags: set[str] = set()
    normalized = []
    for raw_chapter in chapters:
        chapter = _object(raw_chapter, {
            "id", "quest", "required_ending", "requires_flags", "grants_flags",
        }, "campaign chapter")
        chapter_id = _id(chapter["id"], "chapter id")
        if chapter_id in seen_chapters:
            raise CombatSessionError("duplicate campaign chapter id")
        seen_chapters.add(chapter_id)
        quest = normalize_quest(chapter["quest"])
        if quest["world_id"] != world_id:
            raise CombatSessionError("campaign quest world mismatch")
        if quest["quest_id"] in seen_quests:
            raise CombatSessionError("duplicate campaign quest id")
        seen_quests.add(quest["quest_id"])
        required_ending = _id(chapter["required_ending"], "required ending")
        if required_ending not in {item["id"] for item in quest["endings"]}:
            raise CombatSessionError("required campaign ending not authored")
        required_flags = _ids(chapter["requires_flags"], "required flag")
        granted_flags = _ids(chapter["grants_flags"], "granted flag")
        if not set(required_flags) <= available_flags:
            raise CombatSessionError("chapter requires unearned flags")
        if set(granted_flags) & available_flags:
            raise CombatSessionError("campaign flag granted twice")
        available_flags.update(granted_flags)
        if len(available_flags) > MAX_FLAGS:
            raise CombatSessionError("campaign flag budget exceeded")
        normalized.append({
            "id": chapter_id, "quest": quest,
            "required_ending": required_ending,
            "requires_flags": required_flags,
            "grants_flags": granted_flags,
        })
    return {
        "schema_version": SCHEMA, "world_id": world_id,
        "campaign_id": campaign_id, "chapters": normalized,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_campaign(source: Any) -> dict[str, Any]:
    spec = normalize_campaign(source)
    state = {
        "tick": 0, "chapter_index": 0, "phase": "active",
        "flags": [], "history": [],
        "active_quest": new_quest(spec["chapters"][0]["quest"]),
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise CombatSessionError("invalid campaign action")
    if raw["kind"] == "advance":
        _object(raw, {"kind"}, "advance action")
        return {"kind": "advance"}
    if raw["kind"] == "quest":
        _object(raw, {"kind", "action"}, "chapter quest action")
        if type(raw["action"]) is not dict:
            raise CombatSessionError("chapter quest action must be object")
        # Embedded action is canonicalized by the existing quest runtime.
        return {"kind": "quest", "action": raw["action"]}
    raise CombatSessionError("unsupported campaign action")


def _step(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active":
        raise CombatSessionError("campaign already terminal")
    if old["tick"] >= MAX_ACTIONS:
        raise CombatSessionError("campaign action budget exhausted")
    action = _action(raw)
    index = old["chapter_index"]
    chapter = source["chapters"][index]
    active = old["active_quest"]
    history = list(old["history"])
    flags = list(old["flags"])
    phase = "active"
    if action["kind"] == "quest":
        if active["state"]["phase"] != "active":
            raise CombatSessionError("finished chapter must advance")
        active = advance_quest(active, action["action"])
        # The quest runtime stores a canonical normalized action.
        action = {"kind": "quest", "action": active["journal"][-1]["action"]}
    else:
        if active["state"]["phase"] != "finished":
            raise CombatSessionError("chapter quest has not reached an ending")
        active = verify_quest(active)
        ending = active["state"]["ending"]
        won = ending == chapter["required_ending"]
        history.append({
            "chapter_id": chapter["id"], "quest_id": active["source"]["quest_id"],
            "ending": ending, "quest_state_digest": active["state_digest"],
            "accepted": won,
        })
        if not won:
            phase = "blocked"
            active = None
        else:
            if not set(chapter["requires_flags"]) <= set(flags):
                raise CombatSessionError("chapter unlock flags not earned")
            flags = sorted(set(flags) | set(chapter["grants_flags"]))
            index += 1
            if index == len(source["chapters"]):
                phase = "won"
                active = None
            else:
                next_chapter = source["chapters"][index]
                if not set(next_chapter["requires_flags"]) <= set(flags):
                    raise CombatSessionError("next chapter unlock flags missing")
                active = new_quest(next_chapter["quest"])
    state = {
        "tick": old["tick"] + 1, "chapter_index": index,
        "phase": phase, "flags": flags, "history": history,
        "active_quest": active,
    }
    event = {
        "sequence": old["tick"], "action": action,
        "before": snapshot["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": snapshot["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": [*snapshot["journal"], event],
        "save": _save(source, state, snapshot["save"]),
    }
    _size(result, MAX_BYTES)
    return result


def verify_campaign(payload: Any) -> dict[str, Any]:
    """Rebuild every chapter and reward from the original authored actions."""
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "save",
    }, "campaign save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign save")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise CombatSessionError("invalid campaign journal")
    rebuilt = new_campaign(obj["source"])
    for entry in journal:
        if type(entry) is not dict or "action" not in entry:
            raise CombatSessionError("invalid campaign journal event")
        rebuilt = _step(rebuilt, entry["action"])
        if rebuilt["journal"][-1] != entry:
            raise CombatSessionError("campaign event or action mismatch")
    if rebuilt != obj:
        raise CombatSessionError("campaign save/replay lineage mismatch")
    return rebuilt


def resume_campaign(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_campaign(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise CombatSessionError("invalid campaign action batch")
    for action in actions:
        session = _step(session, action)
    return verify_campaign(session)


def simulate_campaign(source: Any, actions: Any) -> dict[str, Any]:
    return resume_campaign(new_campaign(source), actions)


def export_campaign(payload: Any) -> dict[str, Any]:
    session = verify_campaign(payload)
    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "kind": "offline_chapter_campaign",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _size(bundle, MAX_BYTES)
    return bundle


def import_campaign(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "kind", "source_digest", "state_digest",
        "session", "checksum",
    }, "campaign bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA or obj["kind"] != "offline_chapter_campaign":
        raise CombatSessionError("unsupported campaign bundle")
    checksum = obj["checksum"]
    if type(checksum) is not str or len(checksum) != 64:
        raise CombatSessionError("invalid campaign bundle checksum")
    if checksum != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("campaign bundle checksum mismatch")
    session = verify_campaign(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise CombatSessionError("campaign bundle source/state identity mismatch")
    return session


def original_campaign() -> dict[str, Any]:
    """Original two-part Lantern Harbor beacon and night-watch campaign."""
    beacon = original_quest()
    night = json.loads(json.dumps(beacon))
    night["quest_id"] = "night_watch"
    night["expedition"]["expedition_id"] = "night_patrol"
    return {
        "schema_version": SCHEMA, "world_id": "lantern_harbor",
        "campaign_id": "lantern_watch_chronicle",
        "chapters": [
            {
                "id": "beacon", "quest": beacon, "required_ending": "beacon_lit",
                "requires_flags": [], "grants_flags": ["beacon_raised"],
            },
            {
                "id": "night_watch", "quest": night,
                "required_ending": "beacon_lit",
                "requires_flags": ["beacon_raised"],
                "grants_flags": ["harbor_secured"],
            },
        ],
    }


def demo_campaign_actions() -> list[dict[str, Any]]:
    chapter = [{"kind": "quest", "action": action} for action in demo_actions()]
    return [*chapter, {"kind": "advance"}, *chapter, {"kind": "advance"}]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-campaign")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play two original offline chapters")
    sim = sub.add_parser("simulate", help="Run authored campaign actions")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume", help="Continue verified campaign save")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for name in ("verify", "export"):
        command = sub.add_parser(name)
        command.add_argument("--session-json", required=True)
    imp = sub.add_parser("import", help="Replay-check portable campaign bundle")
    imp.add_argument("--bundle-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = simulate_campaign(original_campaign(), demo_campaign_actions())
        elif args.command == "simulate":
            result = simulate_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.actions_json, "campaign actions"),
            )
        elif args.command == "resume":
            result = resume_campaign(
                _parse_json(args.session_json, "campaign save"),
                _parse_json(args.actions_json, "campaign actions"),
            )
        elif args.command == "verify":
            result = verify_campaign(_parse_json(args.session_json, "campaign save"))
        elif args.command == "export":
            result = export_campaign(_parse_json(args.session_json, "campaign save"))
        else:
            result = import_campaign(_parse_json(args.bundle_json, "campaign bundle"))
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
