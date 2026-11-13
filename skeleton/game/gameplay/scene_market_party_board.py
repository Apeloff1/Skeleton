"""Read-only, replay-proven legal turn board for cooperative market players."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    ROLES, _advance, original_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_market_route import _choices
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_board.v1"
MAX_CHOICES = 128


def inspect_party(checkpoint: Any) -> dict[str, Any]:
    session = verify_party(checkpoint)
    state = session["state"]
    player = session["source"]["players"][state["turn_index"]]
    market = state["market"]
    terminal = market["state"]["phase"] != "active"
    candidates = [] if terminal else _choices(market)
    if len(candidates) > MAX_CHOICES:
        raise SceneTravelError("party legal-action inventory budget exceeded")
    actions: list[dict[str, Any]] = []
    if not terminal:
        actions.append({"kind": "pass"})
        for action in candidates:
            role = next((role for role, kind in ROLES.items()
                         if kind == action["kind"]), None)
            if role not in player["roles"]:
                continue
            # Candidate enumeration alone is not proof of legality. The
            # canonical market reducer must accept the action at this head.
            try:
                _advance(session, {"player_id": player["player_id"],
                                   "action": action})
            except SceneTravelError:
                continue
            actions.append(action)
    result = {"schema_version": SCHEMA,
              "source_digest": session["source_digest"],
              "state_digest": session["state_digest"],
              "player_id": player["player_id"], "roles": player["roles"],
              "round": state["round"], "sequence": state["sequence"],
              "phase": market["state"]["phase"],
              "credits": market["state"]["credits"],
              "goods": market["state"]["goods"],
              "reputation": market["state"]["reputation"],
              "legal_actions": actions}
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-board")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("terminal")
    sub.add_parser("inspect").add_argument("--session-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "inspect":
            result = inspect_party(_json(args.session_json))
        else:
            source, turns = original_party()
            result = inspect_party(simulate_party(
                source, turns if args.command == "terminal" else []))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
