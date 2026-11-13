"""Source-bound read-only weather board: legal moves, resources and forecast."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_tile_walk import _bounded, _json
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    forecast, new_weather, original_weather, verify_weather,
)
from skeleton.game.gameplay.scene_weather_route import legal_weather_actions

SCHEMA = "skeleton.scene_weather_board.v1"


def weather_board(session: Any, *, max_choices: int = 32) -> dict[str, Any]:
    if type(max_choices) is not int or not 1 <= max_choices <= 64:
        raise SceneTravelError("invalid weather board action budget")
    current = verify_weather(session)
    state = current["state"]
    tile = state["survival"]["state"]["tile"]["state"]
    scene = tile["scene"]["state"]
    scene_id = scene["scene_id"]
    legal = legal_weather_actions(current)
    result = {
        "schema_version": SCHEMA,
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
        "tick": state["tick"], "phase": state["phase"],
        "scene_id": scene_id, "position": tile["position"],
        "health": state["health"], "stamina": state["stamina"],
        "food": state["survival"]["state"]["food"],
        "inventory": scene["inventory"],
        "owned_gear": state["owned_gear"], "equipped": state["equipped"],
        "forecast_next": (forecast(current["source"], scene_id, state["tick"] + 1)
                          if state["phase"] == "active" else None),
        "legal_actions": legal[:max_choices],
        "choices_truncated": len(legal) > max_choices,
        "hint_kind": "legal_actions_not_guaranteed_win",
    }
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-board")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("inspect")
    p.add_argument("--session-json", required=True)
    p.add_argument("--max-choices", type=int, default=32)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_weather()
            result = weather_board(new_weather(source))
        else:
            result = weather_board(_json(args.session_json),
                                   max_choices=args.max_choices)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
