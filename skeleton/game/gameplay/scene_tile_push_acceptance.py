"""Independent source-to-play-to-restart-to-export push-puzzle acceptance.

This is deterministic contract evidence, not a release or device certificate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_push import (
    MAX_STEPS, _json, edit_push, export_push, import_push,
    legal_push_actions, new_push, normalize_push, original_push,
    resume_push, simulate_push, verify_push,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_tile_push_acceptance.v1"


def accept_push(source: Any, actions: Any) -> dict[str, Any]:
    """Require actual player victory and exact portable restart equality."""
    spec = normalize_push(source)
    if type(actions) is not list or not 1 <= len(actions) <= MAX_STEPS:
        raise SceneTravelError("invalid push acceptance action sequence")
    first = new_push(spec)
    if not legal_push_actions(first):
        raise SceneTravelError("push source has no opening legal actions")
    middle = len(actions) // 2
    partial = resume_push(first, actions[:middle])
    checkpoint = export_push(partial)
    restored = import_push(checkpoint)
    final = resume_push(restored, actions[middle:])
    one_shot = simulate_push(spec, actions)
    if final != one_shot or verify_push(final) != final:
        raise SceneTravelError("push acceptance restart/replay mismatch")
    if final["state"]["phase"] != "won":
        raise SceneTravelError("push acceptance requires earned victory")
    final_bundle = export_push(final)
    if import_push(final_bundle) != final:
        raise SceneTravelError("push acceptance portable export mismatch")
    authored = edit_push(spec, dig(spec), [], actions)
    if authored["source_digest"] != dig(spec) or authored["preview"] != final:
        raise SceneTravelError("push acceptance editor preview mismatch")
    report = {
        "schema_version": SCHEMA,
        "source_digest": final["source_digest"],
        "initial_state_digest": first["state_digest"],
        "checkpoint_state_digest": partial["state_digest"],
        "checkpoint_checksum": checkpoint["checksum"],
        "final_state_digest": final["state_digest"],
        "final_checksum": final_bundle["checksum"],
        "event_bus_digest": final["event_bus_digest"],
        "action_count": len(actions), "phase": final["state"]["phase"],
        "verified_restart": True, "verified_editor_preview": True,
        "verified_export": True,
    }
    report["evidence_digest"] = dig(report)
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-push-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    run = sub.add_parser("accept")
    run.add_argument("--source-json", required=True)
    run.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_push()
        else:
            source = _json(args.source_json)
            actions = _json(args.actions_json)
        report = accept_push(source, actions)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
