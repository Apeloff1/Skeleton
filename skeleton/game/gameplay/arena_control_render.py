"""Readable bounded ASCII tactical capture board from verified canonical saves."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import (
    _encoded, original_actions, original_control, play_control,
    verify_control,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_render.v1"
ACTOR_GLYPHS = "ABCDEFGHIJKLMNOP"
ZONE_GLYPHS = "12345678"


def render_control(raw: Any) -> dict[str, Any]:
    session = verify_control(raw)
    source, state = session["source"], session["state"]
    arena = source["arena"]
    width, height = arena["width"], arena["height"]
    board = [["." for _ in range(width)] for _ in range(height)]
    for x, y in arena["walls"]:
        board[y][x] = "#"
    zones = []
    for index, zone in enumerate(source["zones"]):
        x, y = zone["position"]
        glyph = ZONE_GLYPHS[index]
        board[y][x] = glyph
        zones.append({
            "glyph": glyph, "zone_id": zone["id"],
            "position": zone["position"], "points": zone["points"],
        })
    actors = []
    for index, actor in enumerate(arena["actors"]):
        glyph = ACTOR_GLYPHS[index]
        status = session["arena_session"]["state"]["actors"][actor["id"]]
        x, y = status["position"]
        if status["hp"] > 0:
            board[y][x] = glyph
        actors.append({
            "glyph": glyph, "actor_id": actor["id"], "team": actor["team"],
            "hp": status["hp"], "position": status["position"],
            "alive": status["hp"] > 0,
        })
    rows = ["".join(row) for row in board]
    result = {
        "schema_version": SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "tick": state["tick"], "phase": state["phase"],
        "winner": state["winner"], "scores": state["scores"],
        "rows": rows, "ascii": "\n".join(rows),
        "actors": actors, "zones": zones,
        "legend": {"wall": "#", "floor": "."},
        "claim": "replay_verified_ascii_view",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_render(session: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source_digest", "state_digest", "tick",
        "phase", "winner", "scores", "rows", "ascii", "actors",
        "zones", "legend", "claim", "receipt",
    }, "control-point render")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point render")
    _encoded(obj)
    expected = render_control(session)
    if expected != obj:
        raise CombatSessionError("control-point render does not match replay")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-render")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Render the original playable beacon match")
    render = sub.add_parser("render")
    render.add_argument("--session-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--render-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = render_control(play_control(original_control(), original_actions()))
        elif args.command == "render":
            result = render_control(_parse_json(args.session_json, "control checkpoint"))
        else:
            result = verify_render(
                _parse_json(args.session_json, "control checkpoint"),
                _parse_json(args.render_json, "control render"),
            )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
