"""Optimistic source authoring for replay-verified survival campaigns.

Edits are replayed from the initial authored source. Stale revisions and
invalid stage mutations cannot silently overwrite another creator's work.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_survival_campaign import (
    _json, export_campaign, normalize_campaign,
    original_campaign, simulate_campaign,
)
from skeleton.game.gameplay.scene_survival_campaign_route import solve_campaign
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_survival_campaign_author.v1"
MAX_EDITS = 64


def _edit(source: dict[str, Any], raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid campaign source edit")
    stages = [dict(stage) for stage in source["stages"]]
    spec = {**source, "stages": stages}
    kind = raw.get("kind")
    if kind == "set_required_score":
        _object(raw, {"kind", "value"}, "campaign threshold edit")
        spec["required_score"] = _limit(
            raw["value"], "campaign threshold", 1, 8000)
    elif kind in ("set_reward", "replace_stage_source"):
        _object(raw, {"kind", "stage_id", "value"}, "campaign stage edit")
        stage_id = _id(raw["stage_id"], "campaign stage id")
        matches = [s for s in stages if s["stage_id"] == stage_id]
        if len(matches) != 1:
            raise SceneTravelError("campaign stage not authored")
        if kind == "set_reward":
            matches[0]["reward"] = _limit(
                raw["value"], "campaign stage reward", 1, 1000)
        else:
            matches[0]["survival_source"] = raw["value"]
    elif kind == "append_stage":
        _object(raw, {"kind", "stage"}, "campaign append edit")
        stage = _object(raw["stage"], {
            "stage_id", "survival_source", "reward",
        }, "campaign appended stage")
        stages.append(stage)
    elif kind == "remove_last_stage":
        _object(raw, {"kind", "stage_id"}, "campaign remove edit")
        if len(stages) < 2 or stages[-1]["stage_id"] != raw["stage_id"]:
            raise SceneTravelError("only last optional stage can be removed")
        stages.pop()
    else:
        raise SceneTravelError("unsupported campaign source edit")
    return normalize_campaign(spec)


def _seal(doc: dict[str, Any]) -> dict[str, Any]:
    # Revisions carry the previous receipt. Never hash that stale receipt into
    # the replacement digest: verification hashes exactly the payload without
    # its top-level digest field.
    doc.pop("digest", None)
    doc["digest"] = dig(doc)
    _bounded(doc)
    return doc


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_campaign(source)
    return _seal({
        "schema_version": SCHEMA, "initial_source": spec,
        "source": spec, "source_digest": dig(spec),
        "revision": 0, "edits": [],
    })


def verify_author(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    doc = _object(payload, {
        "schema_version", "initial_source", "source", "source_digest",
        "revision", "edits", "digest",
    }, "campaign author document")
    if doc["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported campaign author document")
    edits = doc["edits"]
    if type(edits) is not list or len(edits) > MAX_EDITS:
        raise SceneTravelError("invalid campaign author edit journal")
    if type(doc["revision"]) is not int or doc["revision"] != len(edits):
        raise SceneTravelError("campaign author revision mismatch")
    initial = normalize_campaign(doc["initial_source"])
    if initial != doc["initial_source"]:
        raise SceneTravelError("noncanonical campaign initial source")
    current = initial
    for edit in edits:
        current = _edit(current, edit)
    if (current != doc["source"]
            or dig(current) != doc["source_digest"]
            or dig({k: v for k, v in doc.items() if k != "digest"})
            != doc["digest"]):
        raise SceneTravelError("campaign author replay mismatch")
    return doc


def apply_author(payload: Any, edit: Any, *, expected_digest: str,
                 expected_revision: int) -> dict[str, Any]:
    doc = verify_author(payload)
    if (type(expected_digest) is not str
            or expected_digest != doc["source_digest"]
            or type(expected_revision) is not int
            or expected_revision != doc["revision"]):
        raise SceneTravelError("stale campaign author revision or digest")
    if len(doc["edits"]) >= MAX_EDITS:
        raise SceneTravelError("campaign author edit budget exhausted")
    source = _edit(doc["source"], edit)
    return verify_author(_seal({
        **doc, "source": source, "source_digest": dig(source),
        "revision": doc["revision"] + 1,
        "edits": [*doc["edits"], edit],
    }))


def preview_author(payload: Any, actions: Any) -> dict[str, Any]:
    doc = verify_author(payload)
    result = simulate_campaign(doc["source"], actions)
    return {
        "schema_version": "skeleton.scene_survival_campaign_preview.v1",
        "revision": doc["revision"], "source_digest": doc["source_digest"],
        "phase": result["state"]["phase"],
        "score": result["state"]["score"],
        "state_digest": result["state_digest"],
        "bundle": export_campaign(result),
    }


def solve_author(payload: Any, *, max_states: int = 1024,
                 max_depth: int = 32) -> dict[str, Any]:
    doc = verify_author(payload)
    return {
        "schema_version": "skeleton.scene_survival_campaign_author_route.v1",
        "revision": doc["revision"], "source_digest": doc["source_digest"],
        "route": solve_campaign(
            doc["source"], max_states=max_states, max_depth=max_depth),
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-survival-campaign-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    init = sub.add_parser("new")
    init.add_argument("--source-json", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("--document-json", required=True)
    edit.add_argument("--edit-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--expected-revision", required=True, type=int)
    for command in ("verify", "preview", "solve"):
        p = sub.add_parser(command)
        p.add_argument("--document-json", required=True)
        if command == "preview":
            p.add_argument("--actions-json", required=True)
        if command == "solve":
            p.add_argument("--max-states", type=int, default=1024)
            p.add_argument("--max-depth", type=int, default=32)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_campaign()
            result = preview_author(new_author(source), actions)
        elif args.command == "new":
            result = new_author(_json(args.source_json))
        elif args.command == "edit":
            result = apply_author(
                _json(args.document_json), _json(args.edit_json),
                expected_digest=args.expected_digest,
                expected_revision=args.expected_revision)
        elif args.command == "verify":
            result = verify_author(_json(args.document_json))
        elif args.command == "preview":
            result = preview_author(
                _json(args.document_json), _json(args.actions_json))
        else:
            result = solve_author(
                _json(args.document_json), max_states=args.max_states,
                max_depth=args.max_depth)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
