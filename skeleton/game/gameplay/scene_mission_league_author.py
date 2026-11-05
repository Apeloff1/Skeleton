"""Transactional scoring authoring for source-bound offline mission leagues.

Scoring edits require the exact prior digest and an empty competition. Once
playable attempts have been submitted, scoring rules are immutable: changing
them requires creating a new league, never rewriting earned history.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_mission import MAX_BYTES as MISSION_BYTES, simulate_mission
from skeleton.game.gameplay.scene_mission_league import (
    MAX_LEAGUE_BYTES, _bounded, inspect_league, new_league,
    normalize_rules, original_rules, submit_league, verify_league,
)
from skeleton.game.gameplay.scene_mission import original_mission
from skeleton.game.gameplay.scene_travel import SceneTravelError, _object

SCHEMA = "skeleton.scene_mission_league_author.v1"
BUNDLE = "skeleton.scene_mission_league_author_bundle.v1"
MAX_EDITS = 16
EDITABLE = frozenset({
    "action_cost", "mission_points", "reputation_multiplier",
    "victory_bonus", "defeat_penalty",
})


def _edits(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise SceneTravelError("invalid scoring edit count")
    result = []
    for item in raw:
        obj = _object(item, {"field", "value"}, "scoring edit")
        field = obj["field"]
        if type(field) is not str or field not in EDITABLE:
            raise SceneTravelError("unsupported scoring edit field")
        if type(obj["value"]) is not int:
            raise SceneTravelError("scoring edit value must be integer")
        result.append({"field": field, "value": obj["value"]})
    if len({item["field"] for item in result}) != len(result):
        raise SceneTravelError("duplicate scoring edit field")
    return sorted(result, key=lambda x: x["field"])


def edit_league(payload: Any, edits: Any, *,
                expected_digest: str) -> dict[str, Any]:
    """Apply a single bounded optimistic scoring transaction."""
    league = verify_league(payload)
    if (type(expected_digest) is not str
            or expected_digest != league["league_digest"]):
        raise SceneTravelError("stale scoring author expected digest")
    if league["entries"]:
        raise SceneTravelError("cannot change scoring after earned attempts")
    clean = _edits(edits)
    rules = dict(league["rules"])
    for item in clean:
        rules[item["field"]] = item["value"]
    rules = normalize_rules(rules)
    if rules == league["rules"]:
        raise SceneTravelError("scoring edit makes no change")
    updated = new_league(league["source"], rules)
    receipt = {
        "schema_version": SCHEMA,
        "before": league,
        "before_digest": league["league_digest"],
        "edits": clean,
        "after": updated,
        "after_digest": updated["league_digest"],
    }
    receipt["receipt_digest"] = dig(receipt)
    _bounded(receipt)
    return receipt


def verify_edit(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "before", "before_digest", "edits",
        "after", "after_digest", "receipt_digest",
    }, "scoring author receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported scoring author receipt")
    before = verify_league(obj["before"])
    expected = edit_league(
        before, obj["edits"], expected_digest=before["league_digest"],
    )
    if expected != obj:
        raise SceneTravelError("scoring author receipt replay mismatch")
    return expected


def preview_edit(payload: Any, actions: Any) -> dict[str, Any]:
    """Play the edited source and derive its score; never grant a preview."""
    receipt = verify_edit(payload)
    session = simulate_mission(receipt["after"]["source"], actions)
    league = submit_league(
        receipt["after"], "author_preview", session,
        expected_digest=receipt["after_digest"],
    )
    return {
        "schema_version": SCHEMA,
        "before_digest": receipt["before_digest"],
        "after_digest": receipt["after_digest"],
        "playable_score": inspect_league(league)["ranking"][0],
        "verified_session_digest": session["state_digest"],
    }


def export_edit(payload: Any) -> dict[str, Any]:
    receipt = verify_edit(payload)
    record = {
        "schema_version": BUNDLE,
        "before_digest": receipt["before_digest"],
        "after_digest": receipt["after_digest"],
        "receipt": receipt,
    }
    record["checksum"] = dig(record)
    _bounded(record)
    return record


def import_edit(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "before_digest", "after_digest", "receipt", "checksum",
    }, "scoring author bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported scoring author bundle")
    if (type(obj["checksum"]) is not str
            or obj["checksum"] != dig({
                k: v for k, v in obj.items() if k != "checksum"
            })):
        raise SceneTravelError("scoring author bundle checksum mismatch")
    receipt = verify_edit(obj["receipt"])
    if (obj["before_digest"] != receipt["before_digest"]
            or obj["after_digest"] != receipt["after_digest"]):
        raise SceneTravelError("scoring author bundle identity mismatch")
    return receipt


def demo_edit() -> dict[str, Any]:
    base = new_league(original_mission(), original_rules())
    return edit_league(
        base, [{"field": "victory_bonus", "value": 250}],
        expected_digest=base["league_digest"],
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-league-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--league-json", required=True)
    edit.add_argument("--edits-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    for name in ("verify", "export"):
        sub.add_parser(name).add_argument("--receipt-json", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--receipt-json", required=True)
    preview.add_argument("--actions-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_edit()
        elif args.command == "edit":
            result = edit_league(
                _strict_json(args.league_json, "league", max_bytes=MAX_LEAGUE_BYTES),
                _strict_json(args.edits_json, "scoring edits", max_bytes=8192),
                expected_digest=args.expected_digest,
            )
        elif args.command == "import":
            result = import_edit(_strict_json(
                args.bundle_json, "scoring author bundle", max_bytes=MAX_LEAGUE_BYTES,
            ))
        else:
            receipt = _strict_json(
                args.receipt_json, "scoring author receipt", max_bytes=MAX_LEAGUE_BYTES,
            )
            if args.command == "verify":
                result = verify_edit(receipt)
            elif args.command == "export":
                result = export_edit(receipt)
            else:
                result = preview_edit(
                    receipt, _strict_json(
                        args.actions_json, "mission actions", max_bytes=MISSION_BYTES,
                    ),
                )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
