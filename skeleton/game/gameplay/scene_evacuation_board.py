"""Legal, replay-proven evacuation choices for CLI, UI and automated play."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_evacuation import (
    MAX_BYTES, _advance, _bounded, new_evacuation, original_evacuation,
    verify_evacuation,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_CHOICES = 96


def legal_evacuation_actions(checkpoint: Any) -> list[dict[str, Any]]:
    session = verify_evacuation(checkpoint)
    source, state = session["source"], session["state"]
    if state["phase"] != "active":
        return []
    mission = state["mission"]
    nested = mission["state"]["scene"]["state"]
    scene_id = nested["scene_id"]
    candidates: list[dict[str, Any]] = [
        {"kind": "wait"}, {"kind": "protect"},
    ]
    candidates.extend(
        {"kind": "rescue", "npc_id": npc["id"]}
        for npc in source["npcs"] if npc["scene_id"] == scene_id
    )
    if mission["state"]["phase"] == "active":
        if nested["phase"] == "active":
            for choice in source["mission"]["choices"]:
                if choice["scene_id"] == scene_id and choice["id"] not in mission["state"]["choices"]:
                    for option in choice["options"]:
                        candidates.append({"kind": "mission", "action": {
                            "kind": "choose", "choice_id": choice["id"],
                            "option_id": option["id"],
                        }})
            scene = next(s for s in source["mission"]["world"]["scenes"]
                         if s["id"] == scene_id)
            for pickup in scene["pickups"]:
                candidates.append({"kind": "mission", "action": {
                    "kind": "scene", "action": {
                        "kind": "collect", "pickup_id": pickup["id"],
                    },
                }})
            for edge in scene["exits"]:
                candidates.append({"kind": "mission", "action": {
                    "kind": "scene", "action": {
                        "kind": "travel", "exit_id": edge["id"],
                    },
                }})
        else:
            for ending in source["mission"]["endings"]:
                if ending["scene_phase"] == nested["phase"]:
                    candidates.append({"kind": "mission", "action": {
                        "kind": "finish", "ending_id": ending["id"],
                    }})
    if len(candidates) > MAX_CHOICES:
        raise SceneTravelError("evacuation candidate budget exceeded")
    legal = []
    for candidate in candidates:
        try:
            _advance(session, candidate)
        except SceneTravelError:
            continue
        legal.append(candidate)
    return legal


def inspect_evacuation(checkpoint: Any) -> dict[str, Any]:
    session = verify_evacuation(checkpoint)
    state = session["state"]
    nested = state["mission"]["state"]["scene"]["state"]
    result = {
        "schema_version": "skeleton.scene_evacuation_board.v1",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "tick": state["tick"], "phase": state["phase"],
        "scene_id": nested["scene_id"],
        "mission_phase": state["mission"]["state"]["phase"],
        "mission_ending": state["mission"]["state"]["ending"],
        "rescued": state["rescued"], "lost": state["lost"],
        "passengers": state["passengers"],
        "capacity": session["source"]["capacity"],
        "required_rescues": session["source"]["required_rescues"],
        "earned_supplies": state["supplies"], "shielded": state["shielded"],
        "reward": state["reward"],
        "legal_actions": legal_evacuation_actions(session),
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-evacuation-board")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("inspect").add_argument("--session-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        checkpoint = (new_evacuation(original_evacuation()) if args.command == "demo"
                      else _strict_json(args.session_json, "evacuation board",
                                        max_bytes=MAX_BYTES))
        print(json.dumps(inspect_evacuation(checkpoint), sort_keys=True,
                         separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
