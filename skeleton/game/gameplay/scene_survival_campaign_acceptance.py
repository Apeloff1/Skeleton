"""End-to-end authored survival campaign acceptance through real gameplay.

An acceptance receipt is issued only after an earned win, deterministic
checkpoint replay and portable import of the exact final state. Checksums
detect corruption, not publisher authenticity or device qualification.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_survival_campaign import (
    _json, export_campaign, import_campaign, original_campaign,
    resume_campaign, simulate_campaign, verify_campaign,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _object

SCHEMA = "skeleton.scene_survival_campaign_acceptance.v1"
BUNDLE = "skeleton.scene_survival_campaign_acceptance_bundle.v1"
MAX_ACTIONS = 512


def accept_campaign(source: Any, actions: Any, *,
                    checkpoint_at: int | None = None) -> dict[str, Any]:
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise SceneTravelError("invalid campaign acceptance action batch")
    _bounded(source)
    _bounded(actions)
    if checkpoint_at is None:
        checkpoint_at = len(actions) // 2
    if (type(checkpoint_at) is not int
            or not 0 <= checkpoint_at <= len(actions)):
        raise SceneTravelError("invalid campaign acceptance checkpoint")
    complete = simulate_campaign(source, actions)
    checkpoint = simulate_campaign(source, actions[:checkpoint_at])
    restored = resume_campaign(checkpoint, actions[checkpoint_at:])
    if restored != complete or verify_campaign(complete) != complete:
        raise SceneTravelError("campaign checkpoint replay mismatch")
    portable = export_campaign(complete)
    if import_campaign(portable) != complete:
        raise SceneTravelError("campaign portable roundtrip mismatch")
    state = complete["state"]
    if (state["phase"] != "won"
            or state["score"] < complete["source"]["required_score"]
            or len(state["completed"]) != len(complete["source"]["stages"])):
        raise SceneTravelError("campaign has no fully earned victory")
    report = {
        "schema_version": SCHEMA, "source": complete["source"],
        "actions": actions, "checkpoint_at": checkpoint_at,
        "source_digest": complete["source_digest"],
        "state_digest": complete["state_digest"],
        "checkpoint_digest": dig(checkpoint),
        "save_digest": dig(complete["save"]),
        "score": state["score"], "completed": state["completed"],
        "phase": "won", "portable_bundle": portable,
    }
    report["receipt"] = dig(report)
    _bounded(report)
    return report


def verify_acceptance(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    report = _object(payload, {
        "schema_version", "source", "actions", "checkpoint_at",
        "source_digest", "state_digest", "checkpoint_digest",
        "save_digest", "score", "completed", "phase",
        "portable_bundle", "receipt",
    }, "campaign acceptance receipt")
    if report["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported campaign acceptance receipt")
    expected = accept_campaign(
        report["source"], report["actions"],
        checkpoint_at=report["checkpoint_at"])
    if expected != report:
        raise SceneTravelError("campaign acceptance receipt mismatch")
    return expected


def export_acceptance(payload: Any) -> dict[str, Any]:
    report = verify_acceptance(payload)
    bundle = {
        "schema_version": BUNDLE,
        "source_digest": report["source_digest"],
        "state_digest": report["state_digest"],
        "acceptance": report,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_acceptance(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    bundle = _object(payload, {
        "schema_version", "source_digest", "state_digest",
        "acceptance", "checksum",
    }, "campaign acceptance export")
    if bundle["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported campaign acceptance export")
    if bundle["checksum"] != dig({
        k: v for k, v in bundle.items() if k != "checksum"
    }):
        raise SceneTravelError("campaign acceptance checksum mismatch")
    report = verify_acceptance(bundle["acceptance"])
    if (report["source_digest"] != bundle["source_digest"]
            or report["state_digest"] != bundle["state_digest"]):
        raise SceneTravelError("campaign acceptance lineage mismatch")
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-survival-campaign-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    run = sub.add_parser("run")
    run.add_argument("--source-json", required=True)
    run.add_argument("--actions-json", required=True)
    run.add_argument("--checkpoint-at", type=int)
    for name in ("verify", "export"):
        sub.add_parser(name).add_argument("--acceptance-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_campaign()
            result = accept_campaign(source, actions)
        elif args.command == "run":
            result = accept_campaign(
                _json(args.source_json), _json(args.actions_json),
                checkpoint_at=args.checkpoint_at)
        elif args.command == "verify":
            result = verify_acceptance(_json(args.acceptance_json))
        elif args.command == "export":
            result = export_acceptance(_json(args.acceptance_json))
        else:
            result = import_acceptance(_json(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
