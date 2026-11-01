"""Portable offline weather-traversal checkpoints with canonical replay.

A bundle is an integrity-checked transport envelope, not a signature or
authorization token. Only canonical source, event journal and save lineage
may determine the restored scene, inventory and weather.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _json, _object
from skeleton.game.gameplay.scene_weather import (
    _export, normalize_weather, original_weather_demo, new_session,
    resume_session, verify_session,
)

SCHEMA = "skeleton.scene_weather_package.v1"


def _manifest(source: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    state = session["state"]
    scene = state["scene"]
    return {
        "world_id": source["world"]["world_id"],
        "source_digest": session["source_digest"],
        "tick": state["tick"], "weather": state["weather"],
        "phase": state["phase"],
        "scene_id": scene["state"]["scene_id"],
        "inventory": list(scene["state"]["inventory"]),
        "collected": list(scene["state"]["collected"]),
        "scene_state_digest": scene["state_digest"],
        "event_bus_digest": session["event_bus_digest"],
        "save_digest": dig(session["save"]),
    }


def package_weather(source: Any, session: Any) -> dict[str, Any]:
    """Export only a replay-verified checkpoint from the same authored source."""
    spec = normalize_weather(source)
    verified = verify_session(session)
    if verified["source_digest"] != dig(spec):
        raise SceneTravelError("portable weather source mismatch")
    report = {
        "schema_version": SCHEMA,
        "source": spec, "source_digest": dig(spec),
        "snapshot": verified, "snapshot_digest": dig(verified),
        "manifest": _manifest(spec, verified),
        "claim": "integrity_checked_offline_weather_save",
    }
    report["receipt"] = dig(report)
    _export(report)
    return report


def verify_package(raw: Any) -> dict[str, Any]:
    """Rebuild the source, weather journal, nested scene and portable manifest."""
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "snapshot",
        "snapshot_digest", "manifest", "claim", "receipt",
    }, "portable weather checkpoint")
    if (obj["schema_version"] != SCHEMA
            or obj["claim"] != "integrity_checked_offline_weather_save"):
        raise SceneTravelError("unsupported portable weather schema")
    _export(obj)
    expected = package_weather(obj["source"], obj["snapshot"])
    if expected != obj:
        raise SceneTravelError("portable weather replay or manifest mismatch")
    return expected


def resume_package(raw: Any, actions: Any) -> dict[str, Any]:
    """Apply legal actions to a verified checkpoint; never trust cached rewards."""
    saved = verify_package(raw)
    if type(actions) is not list:
        raise SceneTravelError("invalid portable weather action list")
    if not actions:
        return saved
    resumed = resume_session(saved["snapshot"], actions)
    return package_weather(saved["source"], resumed)


def original_package_demo() -> dict[str, Any]:
    source, actions = original_weather_demo()
    first = resume_session(new_session(source), actions[:1])
    return package_weather(source, first)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-package")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    pack = sub.add_parser("pack")
    pack.add_argument("--source-json", required=True)
    pack.add_argument("--session-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--package-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--package-json", required=True)
    resume.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_package_demo()
        elif args.command == "pack":
            result = package_weather(
                _json(args.source_json, "weather source"),
                _json(args.session_json, "weather save"),
            )
        elif args.command == "verify":
            result = verify_package(_json(args.package_json, "weather package"))
        else:
            result = resume_package(
                _json(args.package_json, "weather package"),
                _json(args.actions_json, "weather actions"),
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
