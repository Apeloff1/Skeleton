"""End-to-end source, player decisions, restart, replay and export acceptance."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_evacuation import (
    MAX_BYTES, _bounded, demo_actions, export_evacuation, import_evacuation,
    new_evacuation, original_evacuation, resume_evacuation, simulate_evacuation,
    verify_evacuation,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def accept_evacuation(source: Any, actions: Any) -> dict[str, Any]:
    if type(actions) is not list:
        raise SceneTravelError("evacuation acceptance actions must be a list")
    expected = simulate_evacuation(source, actions)
    if expected["state"]["phase"] != "evacuated":
        raise SceneTravelError("evacuation acceptance requires earned victory")
    # Every intermediate checkpoint must replay to the identical terminal state.
    for cut in range(len(actions) + 1):
        checkpoint = simulate_evacuation(source, actions[:cut])
        restored = resume_evacuation(checkpoint, actions[cut:])
        if restored != expected:
            raise SceneTravelError("evacuation restart divergence")
    bundle = export_evacuation(expected)
    if import_evacuation(bundle) != verify_evacuation(expected):
        raise SceneTravelError("evacuation portable roundtrip divergence")
    report = {
        "schema_version": "skeleton.scene_evacuation_acceptance.v1",
        "source_digest": expected["source_digest"],
        "state_digest": expected["state_digest"],
        "event_bus_digest": expected["event_bus_digest"],
        "phase": expected["state"]["phase"],
        "rescued": expected["state"]["rescued"],
        "passengers": expected["state"]["passengers"],
        "lost": expected["state"]["lost"],
        "reward": expected["state"]["reward"],
        "actions": len(actions), "checkpoints_verified": len(actions) + 1,
        "portable_checksum": bundle["checksum"],
    }
    report["receipt"] = dig(report)
    _bounded(report)
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-evacuation-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    accept = sub.add_parser("accept")
    accept.add_argument("--source-json", required=True)
    accept.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = accept_evacuation(original_evacuation(), demo_actions())
        else:
            result = accept_evacuation(
                _strict_json(args.source_json, "evacuation source", max_bytes=MAX_BYTES),
                _strict_json(args.actions_json, "evacuation actions", max_bytes=MAX_BYTES),
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
