"""Interactive offline market quest with bounded input and durable checkpoints.

This interface is intentionally a stream adapter, not a second game engine.
Every accepted action is executed by the canonical market reducer and each
checkpoint can be independently reconstructed from the complete journal.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_market import (
    _advance, _json, new_market, original_market, verify_market,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_BYTES
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_RETRIES = 3


def parse_market_command(raw: str) -> dict[str, Any]:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise SceneTravelError("market command exceeds input budget")
    text = raw.strip()
    if text.startswith("{"):
        obj = _json(text)
        if type(obj) is not dict:
            raise SceneTravelError("market command must be an object")
        return obj
    words = text.split()
    if len(words) != 2:
        raise SceneTravelError("use move/collect/travel/buy/craft/deliver ID or JSON")
    verb, argument = words
    if verb == "move":
        return {"kind": "tile", "action": {
            "kind": "move", "direction": argument,
        }}
    if verb in ("collect", "travel"):
        return {"kind": "tile", "action": {
            "kind": verb,
            "pickup_id" if verb == "collect" else "exit_id": argument,
        }}
    if verb in ("buy", "craft", "deliver"):
        return {
            "kind": verb,
            {"buy": "offer_id", "craft": "recipe_id",
             "deliver": "delivery_id"}[verb]: argument,
        }
    raise SceneTravelError("unsupported market command")


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
    })


def _available(session: dict[str, Any]) -> dict[str, Any]:
    state = session["state"]
    tile = state["tile"]["state"]
    scene = tile["scene"]["state"]["scene_id"]
    pos = tile["position"]
    source = session["source"]
    markets = [
        {"market_id": market["market_id"], "offers": [
            {"offer_id": offer["offer_id"], "price": offer["price"],
             "remaining": offer["stock"] - state["purchases"].get(offer["offer_id"], 0)}
            for offer in market["offers"]
        ]}
        for market in source["markets"]
        if market["scene_id"] == scene and market["at"] == pos
    ]
    recipes = [
        {"recipe_id": recipe["recipe_id"], "inputs": recipe["inputs"],
         "output": recipe["output"]}
        for recipe in source["recipes"]
        if recipe["scene_id"] == scene and recipe["at"] == pos
    ]
    deliveries = [
        {"delivery_id": delivery["delivery_id"], "goods": delivery["goods"]}
        for delivery in source["deliveries"]
        if delivery["scene_id"] == scene and delivery["at"] == pos
        and delivery["delivery_id"] not in state["delivered"]
    ]
    return {
        "event": "market", "tick": state["tick"], "scene_id": scene,
        "position": pos, "credits": state["credits"], "goods": state["goods"],
        "reputation": state["reputation"], "markets": markets,
        "recipes": recipes, "deliveries": deliveries,
        "required_deliveries": source["required_deliveries"],
        "completed_deliveries": state["delivered"],
        "state_digest": session["state_digest"],
    }


def play_market(source: Any = None, *, session: Any = None,
                expected_source_digest: str | None = None,
                checkpoint_every: int = 8,
                input_stream: Any = None,
                output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one market source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("invalid market checkpoint interval")
    current = new_market(source) if session is None else verify_market(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or current["source_digest"] != expected_source_digest):
            raise SceneTravelError("market source digest does not match trusted input")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        _emit(writer, _available(current))
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise SceneTravelError("market input ended; verified checkpoint emitted")
            try:
                action = parse_market_command(line)
                updated = _advance(current, action)
            except (SceneTravelError, ValueError, TypeError, KeyError) as exc:
                _emit(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": MAX_RETRIES - attempt - 1,
                })
                if attempt == MAX_RETRIES - 1:
                    _checkpoint(writer, current, "invalid_commands")
                    raise SceneTravelError(
                        "three invalid market commands; checkpoint emitted"
                    ) from exc
            else:
                current = updated
                _emit(writer, {
                    "event": "accepted", "action": action,
                    "tick": current["state"]["tick"],
                    "state_digest": current["state_digest"],
                })
                break
        if (current["state"]["phase"] == "active"
                and current["state"]["tick"] % checkpoint_every == 0):
            _checkpoint(writer, current, "interval")
    _checkpoint(writer, current, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": current["state"]["phase"],
        "state_digest": current["state_digest"],
        "credits": current["state"]["credits"],
        "reputation": current["state"]["reputation"],
        "delivered": current["state"]["delivered"],
    })
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-play")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    play = sub.add_parser("play")
    group = play.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    play.add_argument("--source-digest")
    play.add_argument("--checkpoint-every", type=int, default=8)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_market()
            commands = []
            for action in actions:
                if action["kind"] == "tile":
                    nested = action["action"]
                    field = "direction" if nested["kind"] == "move" else (
                        "pickup_id" if nested["kind"] == "collect" else "exit_id"
                    )
                    commands.append(nested["kind"] + " " + nested[field])
                else:
                    field = {"buy": "offer_id", "craft": "recipe_id",
                             "deliver": "delivery_id"}[action["kind"]]
                    commands.append(action["kind"] + " " + action[field])
            play_market(source, input_stream=io.StringIO("\n".join(commands) + "\n"))
        else:
            play_market(
                _json(args.source_json) if args.source_json is not None else None,
                session=_json(args.session_json)
                if args.session_json is not None else None,
                expected_source_digest=args.source_digest,
                checkpoint_every=args.checkpoint_every,
            )
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
