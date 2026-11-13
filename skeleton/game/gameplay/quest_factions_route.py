"""Bounded shortest playable faction ending route with replayed witness."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest_interactive import legal_quest_actions
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_factions import (
    MAX_BYTES, _advance, _bounded, export_factions, import_factions,
    new_factions, original_factions, resume_factions, verify_factions,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _parse_json,
)

SCHEMA = "skeleton.quest_factions_route.v1"
MAX_STATES = 1024
MAX_DEPTH = 32


def _limits(states: int, depth: int) -> None:
    if type(states) is not int or not 1 <= states <= MAX_STATES:
        raise CombatSessionError("invalid faction route state budget")
    if type(depth) is not int or not 1 <= depth <= MAX_DEPTH:
        raise CombatSessionError("invalid faction route depth budget")


def _result(start: dict[str, Any], ending: str, status: str,
            actions: list[dict[str, Any]], explored: int, exhausted: bool,
            final: dict[str, Any] | None, states: int, depth: int) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "status": status,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "target_ending": ending,
        "final_state_digest": final["state_digest"] if final else None,
        "portable_checksum": export_factions(final)["checksum"] if final else None,
        "actions": actions, "explored": explored, "budget_exhausted": exhausted,
        "max_states": states, "max_depth": depth,
    }
    result["checksum"] = dig(result)
    _bounded(result, MAX_BYTES)
    return result


def plan_factions(source: Any = None, *, session: Any = None,
                  target_ending: str = "beacon_lit",
                  max_states: int = 128, max_depth: int = 20) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one faction source or checkpoint")
    _limits(max_states, max_depth)
    start = new_factions(source) if session is None else verify_factions(session)
    target = _id(target_ending, "target_ending")
    if target not in {e["id"] for e in start["source"]["quest"]["endings"]}:
        raise CombatSessionError("unknown authored faction ending")
    if start["state"]["phase"] == "finished":
        matched = start["state"]["ending"] == target
        return _result(
            start, target, "found" if matched else "unreachable",
            [], 0, False, start if matched else None, max_states, max_depth,
        )
    queue = deque([(start, ())])
    seen = {start["state_digest"]}
    explored = 0
    exhausted = False
    while queue:
        if explored >= max_states:
            exhausted = True
            break
        current, actions = queue.popleft()
        explored += 1
        if len(actions) >= max_depth:
            if legal_quest_actions(current["state"]["quest"]):
                exhausted = True
            continue
        for action in legal_quest_actions(current["state"]["quest"]):
            try:
                next_state = _advance(current, action)
            except CombatSessionError:
                continue
            path = (*actions, next_state["journal"][-1]["action"])
            if (next_state["state"]["phase"] == "finished" and
                    next_state["state"]["ending"] == target):
                if import_factions(export_factions(next_state)) != next_state:
                    raise CombatSessionError("faction route portable replay mismatch")
                return _result(
                    start, target, "found", list(path), explored, False,
                    next_state, max_states, max_depth,
                )
            if next_state["state"]["phase"] != "active":
                continue
            if next_state["state_digest"] not in seen:
                seen.add(next_state["state_digest"])
                queue.append((next_state, path))
    return _result(
        start, target, "inconclusive" if exhausted else "unreachable",
        [], explored, exhausted, None, max_states, max_depth,
    )


def verify_plan(raw: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    if type(raw) is not dict or raw.get("schema_version") != SCHEMA:
        raise CombatSessionError("invalid faction route receipt")
    if raw.get("status") != "found":
        raise CombatSessionError("only found faction routes have playable witnesses")
    _limits(raw.get("max_states"), raw.get("max_depth"))
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one faction source or checkpoint")
    start = new_factions(source) if session is None else verify_factions(session)
    expected = plan_factions(
        session=start, target_ending=raw.get("target_ending"),
        max_states=raw["max_states"], max_depth=raw["max_depth"],
    )
    if expected != raw:
        raise CombatSessionError("faction route search receipt mismatch")
    final = resume_factions(start, raw["actions"])
    if (final["state"]["phase"] != "finished" or
            final["state"]["ending"] != raw["target_ending"] or
            final["state_digest"] != raw["final_state_digest"] or
            export_factions(final)["checksum"] != raw["portable_checksum"]):
        raise CombatSessionError("faction route witness replay mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-factions-route")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--ending-id", default="beacon_lit")
    parser.add_argument("--max-states", type=int, default=128)
    parser.add_argument("--max-depth", type=int, default=20)
    parser.add_argument("--verify-json")
    args = parser.parse_args(list(argv))
    try:
        source = (
            original_factions() if args.demo else
            _parse_json(args.source_json, "faction source")
            if args.source_json is not None else None
        )
        session = (
            _parse_json(args.session_json, "faction checkpoint")
            if args.session_json is not None else None
        )
        if args.verify_json is None:
            result = plan_factions(
                source, session=session, target_ending=args.ending_id,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            final = verify_plan(
                _parse_json(args.verify_json, "faction route receipt"),
                source=source, session=session,
            )
            result = {
                "ok": True, "ending": final["state"]["ending"],
                "state_digest": final["state_digest"],
                "portable_checksum": export_factions(final)["checksum"],
            }
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("faction route CLI output exceeds size budget")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
