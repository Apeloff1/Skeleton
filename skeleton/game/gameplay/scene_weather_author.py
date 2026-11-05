"""Transactional weather source editing and replay-safe previews."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_walk import _bounded, _json
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object
from skeleton.game.gameplay.scene_weather import (
    MAX_PHASES, MAX_SOURCE_BYTES, forecast, normalize_weather, original_weather,
    simulate_weather,
)

MAX_EDITS = 64


def edit_weather(source: Any, edits: Any, *,
                 expected_digest: str | None = None) -> dict[str, Any]:
    """Apply all source edits or none; refuse stale editor state and invalid previews."""
    spec = normalize_weather(source)
    if expected_digest is not None and (
        type(expected_digest) is not str or expected_digest != dig(spec)
    ):
        raise SceneTravelError("stale weather source edit lease")
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise SceneTravelError("invalid weather edit batch")
    candidate = copy.deepcopy(spec)
    for raw in edits:
        if type(raw) is not dict:
            raise SceneTravelError("invalid weather edit")
        kind = raw.get("kind")
        if kind == "replace_phase":
            item = _object(raw, {
                "kind", "scene_id", "index", "phase",
            }, "weather phase edit")
            scene_id = _id(item["scene_id"], "weather edit scene")
            climate = next(
                (c for c in candidate["climates"] if c["scene_id"] == scene_id),
                None)
            if climate is None:
                raise SceneTravelError("unknown climate edit scene")
            index = _limit(item["index"], "weather phase index", 0, MAX_PHASES - 1)
            if index >= len(climate["phases"]):
                raise SceneTravelError("weather phase index outside authored phases")
            climate["phases"][index] = copy.deepcopy(item["phase"])
        elif kind == "set_gear":
            item = _object(raw, {"kind", "gear"}, "weather equipment edit")
            if type(item["gear"]) is not dict:
                raise SceneTravelError("invalid equipment edit")
            ident = _id(item["gear"].get("gear_id"), "weather gear edit id")
            candidate["gear"] = [
                gear for gear in candidate["gear"] if gear["gear_id"] != ident
            ] + [copy.deepcopy(item["gear"])]
        elif kind == "remove_gear":
            item = _object(raw, {"kind", "gear_id"}, "remove equipment")
            ident = _id(item["gear_id"], "weather gear removal")
            previous = len(candidate["gear"])
            candidate["gear"] = [
                gear for gear in candidate["gear"] if gear["gear_id"] != ident
            ]
            if len(candidate["gear"]) == previous:
                raise SceneTravelError("cannot remove unknown equipment")
        else:
            raise SceneTravelError("unsupported weather editor operation")
    candidate = normalize_weather(candidate)
    _bounded(candidate, MAX_SOURCE_BYTES)
    return {
        "schema_version": "skeleton.scene_weather_edit.v1",
        "previous_digest": dig(spec), "source_digest": dig(candidate),
        "source": candidate, "applied_edits": len(edits),
    }


def preview_weather(source: Any, actions: Any) -> dict[str, Any]:
    session = simulate_weather(source, actions)
    scene = session["state"]["survival"]["state"]["tile"]["state"]["scene"]["state"]["scene_id"]
    return {
        "schema_version": "skeleton.scene_weather_preview.v1",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "phase": session["state"]["phase"],
        "health": session["state"]["health"],
        "stamina": session["state"]["stamina"],
        "equipped": session["state"]["equipped"],
        "forecast_next": forecast(
            session["source"], scene,
            min(session["state"]["tick"] + 1, 256)),
        "session": session,
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("edit")
    p.add_argument("--source-json", required=True)
    p.add_argument("--edits-json", required=True)
    p.add_argument("--expected-digest")
    p = sub.add_parser("preview")
    p.add_argument("--source-json", required=True)
    p.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_weather()
            result = preview_weather(source, actions)
        elif args.command == "edit":
            result = edit_weather(
                _json(args.source_json), _json(args.edits_json),
                expected_digest=args.expected_digest)
        else:
            result = preview_weather(
                _json(args.source_json), _json(args.actions_json))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
