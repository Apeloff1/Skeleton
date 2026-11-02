"""Transactional creator editing for replay-proven market choice forks.

Edits apply to a verified preview, never to the player's canonical checkpoint.
Every resulting candidate is normalized and replayed before publication.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, _json
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS
from skeleton.game.gameplay.scene_market_fork import (
    MAX_CANDIDATES, evaluate_market_fork, normalize_candidates, original_fork,
    verify_market_fork,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_fork_author.v1"
MAX_EDITS = 32


def _normalize_edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid fork editor command")
    kind = raw.get("kind")
    if kind in ("add", "replace"):
        obj = _object(raw, {"kind", "candidate"}, "fork editor candidate")
        candidate = normalize_candidates([obj["candidate"]], remaining=MAX_STEPS)[0]
        return {"kind": kind, "candidate": candidate}
    if kind == "remove":
        obj = _object(raw, {"kind", "candidate_id"}, "fork editor removal")
        return {"kind": kind, "candidate_id": _id(obj["candidate_id"], "fork candidate id")}
    if kind == "rename":
        obj = _object(raw, {
            "kind", "candidate_id", "new_candidate_id",
        }, "fork editor rename")
        return {
            "kind": kind,
            "candidate_id": _id(obj["candidate_id"], "fork candidate id"),
            "new_candidate_id": _id(obj["new_candidate_id"], "new fork candidate id"),
        }
    raise SceneTravelError("unsupported fork editor operation")


def edit_market_fork(report: Any, edits: Any) -> dict[str, Any]:
    """Apply an all-or-nothing authoring transaction and replay every future."""
    before = verify_market_fork(report)
    _bounded(edits, 128 * 1024)
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise SceneTravelError("invalid fork editor batch")
    clean = [_normalize_edit(item) for item in edits]
    by_id = {
        item["candidate_id"]: copy.deepcopy(item)
        for item in before["candidates"]
    }
    for edit in clean:
        kind = edit["kind"]
        if kind in ("add", "replace"):
            candidate = edit["candidate"]
            name = candidate["candidate_id"]
            if (kind == "add" and name in by_id
                    or kind == "replace" and name not in by_id):
                raise SceneTravelError("fork editor candidate conflict")
            by_id[name] = candidate
        elif kind == "remove":
            name = edit["candidate_id"]
            if name not in by_id:
                raise SceneTravelError("fork editor unknown candidate")
            del by_id[name]
        else:
            name, new = edit["candidate_id"], edit["new_candidate_id"]
            if name not in by_id or new in by_id:
                raise SceneTravelError("fork editor rename conflict")
            by_id[new] = {**by_id.pop(name), "candidate_id": new}
        if len(by_id) > MAX_CANDIDATES:
            raise SceneTravelError("fork editor candidate budget exceeded")
    # A published preview must always have at least one authored alternative.
    updated = evaluate_market_fork(before["checkpoint"], list(by_id.values()))
    receipt = {
        "schema_version": SCHEMA,
        "before": before,
        "edits": clean,
        "after": updated,
        "before_digest": dig(before),
        "after_digest": dig(updated),
        "edit_digest": dig(clean),
        "qualification": "transactional_offline_authoring",
    }
    receipt["checksum"] = dig(receipt)
    _bounded(receipt)
    return receipt


def verify_market_fork_edit(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "before", "edits", "after", "before_digest",
        "after_digest", "edit_digest", "qualification", "checksum",
    }, "fork editor receipt")
    if obj["schema_version"] != SCHEMA or obj["qualification"] != "transactional_offline_authoring":
        raise SceneTravelError("invalid fork editor receipt schema")
    expected = edit_market_fork(obj["before"], obj["edits"])
    if obj != expected:
        raise SceneTravelError("fork editor receipt replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-fork-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--report-json", required=True)
    edit.add_argument("--edits-json", required=True)
    sub.add_parser("verify").add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = edit_market_fork(original_fork(), [{
                "kind": "rename", "candidate_id": "complete_delivery",
                "new_candidate_id": "earned_victory",
            }])
        elif args.command == "edit":
            result = edit_market_fork(_json(args.report_json), _json(args.edits_json))
        else:
            result = verify_market_fork_edit(_json(args.receipt_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
