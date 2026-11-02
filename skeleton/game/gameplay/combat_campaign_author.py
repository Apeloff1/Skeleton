"""Transactional authored human combat campaigns with playable source-bound previews.

The editor does not modify live sessions. Every edit uses an exact source
lease, canonical schema normalization, and replayed preview/save/export.
Receipts are integrity checks, never author identity or permission proofs.
"""
from __future__ import annotations

import argparse
import copy
from collections.abc import Sequence
import json
import sys
from typing import Any

from skeleton.game.gameplay.combat_campaign import (
    MAX_CURRENCY, MAX_ENCOUNTER_TURNS, normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.combat_campaign_decision_board import decision_board
from skeleton.game.gameplay.combat_campaign_player import (
    _bounded, demo_player_campaign, export_player_campaign,
    import_player_campaign, new_player_campaign, resume_player_campaign,
    verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_author.v1"
MAX_EDITS = 16
STAT_BOUNDS = {
    "max_hp": (1, 10000), "attack": (1, 1000),
    "defense": (0, 1000), "speed": (0, 1000),
}


def _edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid campaign edit")
    kind = raw.get("kind")
    if kind == "set_reward":
        obj = _object(raw, {"kind", "encounter_id", "reward"}, "reward edit")
        return {"kind": kind, "encounter_id": _id(obj["encounter_id"], "encounter_id"),
                "reward": _integer(obj["reward"], "reward", 0, MAX_CURRENCY)}
    if kind == "set_turn_limit":
        obj = _object(raw, {"kind", "encounter_id", "turn_limit"}, "turn edit")
        return {"kind": kind, "encounter_id": _id(obj["encounter_id"], "encounter_id"),
                "turn_limit": _integer(obj["turn_limit"], "turn_limit",
                                       1, MAX_ENCOUNTER_TURNS)}
    if kind == "set_actor_stat":
        obj = _object(raw, {
            "kind", "encounter_id", "actor_id", "field", "value",
        }, "actor edit")
        field = obj["field"]
        if type(field) is not str or field not in STAT_BOUNDS:
            raise CombatSessionError("unsupported campaign actor stat")
        low, high = STAT_BOUNDS[field]
        return {
            "kind": kind,
            "encounter_id": _id(obj["encounter_id"], "encounter_id"),
            "actor_id": _id(obj["actor_id"], "actor_id"),
            "field": field,
            "value": _integer(obj["value"], field, low, high),
        }
    if kind == "reorder_encounters":
        obj = _object(raw, {"kind", "encounter_ids"}, "reorder edit")
        ids = obj["encounter_ids"]
        if type(ids) is not list or not 1 <= len(ids) <= 4:
            raise CombatSessionError("invalid campaign encounter order")
        ids = [_id(value, "encounter_id") for value in ids]
        if len(set(ids)) != len(ids):
            raise CombatSessionError("duplicate encounter in order")
        return {"kind": kind, "encounter_ids": ids}
    raise CombatSessionError("unsupported campaign edit kind")


def _apply(source: dict[str, Any], edit: dict[str, Any]) -> None:
    entries = source["encounters"]
    if edit["kind"] == "reorder_encounters":
        order = edit["encounter_ids"]
        current = {entry["scenario"]["encounter_id"]: entry for entry in entries}
        if set(order) != set(current) or len(order) != len(entries):
            raise CombatSessionError("reorder must preserve every encounter")
        source["encounters"] = [current[encounter_id] for encounter_id in order]
        return
    entry = next((e for e in entries
                  if e["scenario"]["encounter_id"] == edit["encounter_id"]), None)
    if entry is None:
        raise CombatSessionError("unknown campaign encounter")
    if edit["kind"] == "set_reward":
        entry["reward"] = edit["reward"]
    elif edit["kind"] == "set_turn_limit":
        entry["scenario"]["turn_limit"] = edit["turn_limit"]
    else:
        actor_id = edit["actor_id"]
        if actor_id == source["hero_id"]:
            # Hero stats are a canonical campaign-wide invariant.
            targets = [e["scenario"] for e in entries]
        else:
            targets = [entry["scenario"]]
        for scenario in targets:
            actor = next((a for a in scenario["actors"]
                          if a["id"] == actor_id), None)
            if actor is None:
                raise CombatSessionError("unknown campaign actor")
            actor[edit["field"]] = edit["value"]


def author_campaign(source: Any, edits: Any, expected_source_digest: Any,
                    *, preview_actions: Any = None) -> dict[str, Any]:
    """Apply a bounded atomic edit batch, then play and export its result."""
    before = normalize_campaign(source)
    if (type(expected_source_digest) is not str
            or expected_source_digest != dig(before)):
        raise CombatSessionError("stale campaign author source lease")
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise CombatSessionError("invalid campaign author edit batch")
    _bounded(edits)
    if preview_actions is None:
        preview_actions = []
    if type(preview_actions) is not list or len(preview_actions) > 128:
        raise CombatSessionError("invalid campaign preview actions")
    _bounded(preview_actions)
    normalized = [_edit(edit) for edit in edits]
    after = copy.deepcopy(before)
    events: list[dict[str, Any]] = []
    for index, edit in enumerate(normalized):
        prior = dig(after)
        _apply(after, edit)
        after = normalize_campaign(after)
        event = {
            "revision": index + 1, "before_digest": prior,
            "after_digest": dig(after), "edit": edit,
        }
        event["receipt"] = dig(event)
        events.append(event)
    if after == before:
        raise CombatSessionError("campaign author batch makes no change")
    preview = resume_player_campaign(new_player_campaign(after), preview_actions)
    if verify_player_campaign(preview) != preview:
        raise CombatSessionError("campaign author preview replay mismatch")
    bundle = export_player_campaign(preview)
    if import_player_campaign(bundle) != preview:
        raise CombatSessionError("campaign author portable preview mismatch")
    board = (decision_board(preview)
             if preview["state"]["phase"] == "active" else None)
    result = {
        "schema_version": SCHEMA,
        "before": before, "before_digest": dig(before),
        "edits": normalized, "events": events,
        "after": after, "after_digest": dig(after),
        "preview_actions": preview_actions, "preview": preview,
        "preview_board": board, "preview_bundle": bundle,
        "proof_kind": "canonical_editor_replay_not_author_signature",
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def verify_author_report(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "before", "before_digest", "edits", "events",
        "after", "after_digest", "preview_actions", "preview",
        "preview_board", "preview_bundle", "proof_kind", "receipt",
    }, "campaign author report")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign author report")
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("campaign author receipt mismatch")
    rebuilt = author_campaign(
        obj["before"], obj["edits"], obj["before_digest"],
        preview_actions=obj["preview_actions"],
    )
    if rebuilt != obj:
        raise CombatSessionError("campaign author source or preview replay mismatch")
    return rebuilt


def demo_author() -> dict[str, Any]:
    source = original_campaign()
    demo = demo_player_campaign()
    return author_campaign(
        source, [{"kind": "set_reward", "encounter_id": "reed_watch",
                  "reward": 12}],
        dig(normalize_campaign(source)),
        preview_actions=[event["action"] for event in demo["journal"]],
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    run = sub.add_parser("run")
    run.add_argument("--source-json", required=True)
    run.add_argument("--edits-json", required=True)
    run.add_argument("--expected-source-digest", required=True)
    run.add_argument("--preview-actions-json")
    sub.add_parser("verify").add_argument("--report-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = demo_author()
        elif args.command == "run":
            result = author_campaign(
                _parse_json(args.source_json, "campaign author source"),
                _parse_json(args.edits_json, "campaign author edits"),
                args.expected_source_digest,
                preview_actions=(
                    _parse_json(args.preview_actions_json, "campaign preview actions")
                    if args.preview_actions_json is not None else None
                ),
            )
        else:
            result = verify_author_report(
                _parse_json(args.report_json, "campaign author report"))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            RecursionError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
