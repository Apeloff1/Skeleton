"""Replay-derived NPC rescue endings and consequence comparisons.

No narrative outcome is accepted from client state: every ending, witness and
branch comparison is rebuilt from the canonical weather-rescue action journal.
Active journeys produce an unfinished checkpoint, never a fabricated victory.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _json, _object
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_rescue import (
    original_rescue, play_rescue, verify_rescue,
)

SCHEMA = "skeleton.weather_rescue_epilogue.v1"
COMPARISON_SCHEMA = "skeleton.weather_rescue_epilogue_comparison.v1"


def _story(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = snapshot["source"]
    state = snapshot["state"]
    lines = []
    survivors = []
    lost = []
    waiting = []
    for npc in source["npcs"]:
        identifier = npc["npc_id"]
        status = state["npcs"][identifier]["status"]
        exposure = state["npcs"][identifier]["exposure"]
        if status == "safe":
            survivors.append(identifier)
            line = (identifier + " reached shelter at " + npc["shelter_scene"]
                    + "; the caravan earned " + str(npc["reward"])
                    + " for the rescue.")
        elif status == "lost":
            lost.append(identifier)
            line = (identifier + " was not brought to safety before the "
                    "journey's deadline or weather exposure limit.")
        elif status == "escorting":
            waiting.append(identifier)
            line = (identifier + " is still travelling with the caravan; "
                    "the rescue has not been settled.")
        else:
            waiting.append(identifier)
            line = (identifier + " remains at " + npc["origin_scene"]
                    + " and awaits a rescue.")
        lines.append({"npc_id": identifier, "status": status,
                      "storm_exposure": exposure, "text": line})
    if state["phase"] == "won":
        heading = "All rescued: the lantern caravan returned with everyone safe."
    elif state["phase"] == "lost":
        heading = "The journey ended with unfinished or lost rescues."
    else:
        heading = "The rescue is still underway; no ending has been awarded."
    return {"heading": heading, "lines": lines,
            "safe_npcs": survivors, "lost_npcs": lost,
            "unresolved_npcs": waiting, "earned": state["earned"],
            "tick": state["tick"], "phase": state["phase"]}


def epilogue_rescue(raw: Any) -> dict[str, Any]:
    session = verify_rescue(raw)
    story = _story(session)
    result = {
        "schema_version": SCHEMA, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
        "session": session, "story": story,
        "claim": "offline_replay_checked_not_authenticated",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_epilogue(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "source_digest", "state_digest",
                        "save_digest", "session", "story", "claim", "receipt"},
                  "rescue epilogue")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_replay_checked_not_authenticated":
        raise SceneTravelError("unsupported rescue epilogue")
    _export(obj)
    expected = epilogue_rescue(obj["session"])
    if expected != obj:
        raise SceneTravelError("rescue epilogue consequence or replay mismatch")
    return expected


def _first_divergence(first: list[dict[str, Any]],
                      second: list[dict[str, Any]]) -> int | None:
    for index in range(max(len(first), len(second))):
        if index >= len(first) or index >= len(second):
            return index
        if first[index]["action"] != second[index]["action"]:
            return index
    return None


def compare_rescue_endings(raw_first: Any, raw_second: Any) -> dict[str, Any]:
    first = verify_rescue(raw_first)
    second = verify_rescue(raw_second)
    if first["source_digest"] != second["source_digest"]:
        raise SceneTravelError("rescue comparison source mismatch")
    left, right = _story(first), _story(second)
    ids = [npc["npc_id"] for npc in first["source"]["npcs"]]
    changes = []
    for identifier in ids:
        before = first["state"]["npcs"][identifier]
        after = second["state"]["npcs"][identifier]
        if before != after:
            changes.append({
                "npc_id": identifier, "before": before, "after": after,
            })
    comparison = {
        "first": epilogue_rescue(first),
        "second": epilogue_rescue(second),
        "source_digest": first["source_digest"],
        "first_divergence": _first_divergence(
            first["state"]["journal"], second["state"]["journal"]),
        "earned_delta": right["earned"] - left["earned"],
        "safe_delta": len(right["safe_npcs"]) - len(left["safe_npcs"]),
        "changed_npcs": changes,
        "outcomes_equal": left == right,
    }
    result = {
        "schema_version": COMPARISON_SCHEMA,
        "comparison": comparison,
        "claim": "offline_replay_checked_not_authenticated",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_comparison(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "comparison", "claim", "receipt"},
                  "rescue epilogue comparison")
    if obj["schema_version"] != COMPARISON_SCHEMA or obj["claim"] != "offline_replay_checked_not_authenticated":
        raise SceneTravelError("unsupported rescue epilogue comparison")
    _export(obj)
    comparison = _object(obj["comparison"], {
        "first", "second", "source_digest", "first_divergence", "earned_delta",
        "safe_delta", "changed_npcs", "outcomes_equal",
    }, "rescue epilogue comparison detail")
    expected = compare_rescue_endings(
        verify_epilogue(comparison["first"])["session"],
        verify_epilogue(comparison["second"])["session"])
    if expected != obj:
        raise SceneTravelError("rescue comparison receipt or replay mismatch")
    return expected


def original_epilogue() -> dict[str, Any]:
    source, actions = original_rescue()
    return epilogue_rescue(play_rescue(source, actions))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-rescue-epilogue")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original rescue and narrate verified outcome")
    render = sub.add_parser("render")
    render.add_argument("--session-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--epilogue-json", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--first-json", required=True)
    compare.add_argument("--second-json", required=True)
    verify_compare = sub.add_parser("verify-comparison")
    verify_compare.add_argument("--comparison-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_epilogue()
        elif args.command == "render":
            result = epilogue_rescue(_json(args.session_json, "rescue checkpoint"))
        elif args.command == "verify":
            result = verify_epilogue(_json(args.epilogue_json, "rescue epilogue"))
        elif args.command == "compare":
            result = compare_rescue_endings(
                _json(args.first_json, "first rescue checkpoint"),
                _json(args.second_json, "second rescue checkpoint"))
        else:
            result = verify_comparison(_json(args.comparison_json, "rescue comparison"))
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
