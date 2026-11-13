"""Transactional authoring and replay-verified previews for combat contracts.

Edits are applied to a copy under an exact source-digest lease. Neither an
editor nor its preview may grant gameplay rewards: preview actions run the
canonical combat contract engine and all receipts are reproducible.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json, original_demo,
)
from skeleton.game.gameplay.combat_contract import (
    MAX_SESSION_BYTES, _bounded, normalize_contract, original_contract,
    simulate_contract,
)

SCHEMA = "skeleton.combat_contract_author.v1"
MAX_EDITS = 32


def _normalize_edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid contract author edit")
    kind = raw.get("kind")
    if kind == "set_reward":
        obj = _object(raw, {"kind", "credits", "item_id"}, "reward edit")
        return {
            "kind": kind,
            "credits": _integer(obj["credits"], "credits", 0, 10000),
            "item_id": _id(obj["item_id"], "item_id"),
        }
    if kind == "add_objective":
        obj = _object(raw, {"kind", "objective"}, "add objective edit")
        if type(obj["objective"]) is not dict:
            raise CombatSessionError("invalid added objective")
        return {"kind": kind, "objective": copy.deepcopy(obj["objective"])}
    if kind == "remove_objective":
        obj = _object(raw, {"kind", "objective_id"}, "remove objective edit")
        return {"kind": kind, "objective_id": _id(obj["objective_id"], "objective_id")}
    if kind == "set_player_team":
        obj = _object(raw, {"kind", "team"}, "player team edit")
        return {"kind": kind, "team": _id(obj["team"], "team")}
    raise CombatSessionError("unsupported contract author edit")


def author_contract(source: Any, edits: Any, expected_digest: Any,
                    preview_actions: Any = None) -> dict[str, Any]:
    before = normalize_contract(source)
    if type(expected_digest) is not str or expected_digest != dig(before):
        raise CombatSessionError("contract author source lease mismatch")
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise CombatSessionError("invalid contract edit batch")
    _bounded(edits, MAX_SESSION_BYTES)
    operations = [_normalize_edit(raw) for raw in edits]
    after = copy.deepcopy(before)
    for op in operations:
        if op["kind"] == "set_reward":
            after["reward"] = {"credits": op["credits"], "item_id": op["item_id"]}
        elif op["kind"] == "set_player_team":
            after["player_team"] = op["team"]
        elif op["kind"] == "add_objective":
            after["objectives"].append(copy.deepcopy(op["objective"]))
        else:
            index = next(
                (i for i, x in enumerate(after["objectives"])
                 if x["id"] == op["objective_id"]), None,
            )
            if index is None:
                raise CombatSessionError("cannot remove unknown objective")
            after["objectives"].pop(index)
    after = normalize_contract(after)
    if before == after:
        raise CombatSessionError("contract edit batch makes no change")
    if preview_actions is not None:
        if type(preview_actions) is not list:
            raise CombatSessionError("invalid preview action batch")
        preview = simulate_contract(after, preview_actions)
    else:
        preview = None
    report = {
        "schema_version": SCHEMA,
        "before": before, "before_digest": dig(before),
        "edits": operations, "after": after, "after_digest": dig(after),
        "preview_actions": preview_actions,
        "preview": preview,
    }
    report["receipt"] = dig(report)
    _bounded(report, MAX_SESSION_BYTES)
    return report


def verify_author_report(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_SESSION_BYTES)
    obj = _object(raw, {
        "schema_version", "before", "before_digest", "edits", "after",
        "after_digest", "preview_actions", "preview", "receipt",
    }, "contract author report")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported contract author report")
    rebuilt = author_contract(
        obj["before"], obj["edits"], obj["before_digest"],
        preview_actions=obj["preview_actions"],
    )
    if rebuilt != obj:
        raise CombatSessionError("contract author replay mismatch")
    return rebuilt


def demo_author() -> dict[str, Any]:
    source = original_contract()
    _, actions = original_demo()
    return author_contract(
        source,
        [{"kind": "set_reward", "credits": 24, "item_id": "bridge_veteran_pass"}],
        dig(normalize_contract(source)),
        preview_actions=actions,
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-contract-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    run = sub.add_parser("run")
    run.add_argument("--source-json", required=True)
    run.add_argument("--edits-json", required=True)
    run.add_argument("--expected-digest", required=True)
    run.add_argument("--preview-actions-json")
    sub.add_parser("verify").add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_author()
        elif args.command == "run":
            result = author_contract(
                _parse_json(args.source_json, "author source"),
                _parse_json(args.edits_json, "author edits"),
                args.expected_digest,
                preview_actions=(
                    _parse_json(args.preview_actions_json, "preview actions")
                    if args.preview_actions_json is not None else None
                ),
            )
        else:
            result = verify_author_report(_parse_json(args.report_json, "author report"))
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
