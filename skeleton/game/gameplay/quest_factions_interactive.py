"""Interactive offline faction quest with source-fenced replay checkpoints.

JSON-line protocol deliberately exposes legal actions, never arbitrary state
mutation. Every accepted action runs through canonical quest and faction
transitions; saved checkpoints can be resumed and exported without network.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import MAX_ACTIONS
from skeleton.game.gameplay.expedition_quest_interactive import legal_quest_actions
from skeleton.game.gameplay.quest_factions import (
    _advance, export_factions, new_factions, original_factions, verify_factions,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json,
)

MAX_INPUT_BYTES = 16384
MAX_CHECKPOINT_INTERVAL = 32
MAX_REJECTED_INPUTS = 8


def legal_faction_actions(session: Any) -> list[dict[str, Any]]:
    """Only show actions accepted by BOTH quest and faction consequence gates."""
    saved = verify_factions(session)
    if saved["state"]["phase"] != "active":
        return []
    actions = []
    for action in legal_quest_actions(saved["state"]["quest"]):
        try:
            _advance(saved, action)
        except CombatSessionError:
            continue
        actions.append(action)
    return actions


def _frame(kind: str, session: dict[str, Any], *,
           include_save: bool = False,
           actions: list[dict[str, Any]] | None = None,
           error: str | None = None) -> dict[str, Any]:
    state = session["state"]
    result = {
        "schema_version": "skeleton.quest_factions_play_frame.v1",
        "kind": kind, "tick": state["tick"], "phase": state["phase"],
        "ending": state["ending"],
        "location": state["quest"]["state"]["location"],
        "standing": dict(sorted(state["standing"].items())),
        "inventory": dict(sorted(state["quest"]["state"]["items"].items())),
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "actions": actions,
        "error": error,
    }
    if include_save:
        result["checkpoint"] = session
    return result


def play_factions(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8, max_turns: int = MAX_ACTIONS,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one faction source or checkpoint")
    if (type(checkpoint_every) is not int or
            not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL):
        raise CombatSessionError("invalid faction checkpoint interval")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_ACTIONS:
        raise CombatSessionError("invalid faction play turn budget")
    current = new_factions(source) if session is None else verify_factions(session)
    if expected_source_digest is not None and (
        type(expected_source_digest) is not str or
        expected_source_digest != current["source_digest"]
    ):
        raise CombatSessionError("faction trusted source digest mismatch")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream

    def emit(value: dict[str, Any]) -> None:
        writer.write(json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ) + "\n")
        if hasattr(writer, "flush"):
            writer.flush()

    rejected = 0
    accepted = 0
    while current["state"]["phase"] == "active" and accepted < max_turns:
        legal = legal_faction_actions(current)
        emit(_frame("prompt", current, actions=legal))
        line = reader.readline(MAX_INPUT_BYTES + 1)
        if line == "":
            emit(_frame("checkpoint", current, include_save=True))
            return current
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise CombatSessionError("faction play input size budget exceeded")
        try:
            message = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("non-finite faction play JSON")
            ))
        except (TypeError, ValueError, RecursionError) as exc:
            rejected += 1
            emit(_frame("rejected", current, error="invalid JSON command"))
            if rejected >= MAX_REJECTED_INPUTS:
                raise CombatSessionError("faction play rejected input budget exhausted") from exc
            continue
        if type(message) is not dict:
            rejected += 1
            emit(_frame("rejected", current, error="invalid command envelope"))
            if rejected >= MAX_REJECTED_INPUTS:
                raise CombatSessionError("faction play rejected input budget exhausted")
            continue
        if set(message) == {"command"} and message["command"] in ("save", "quit", "export"):
            if message["command"] == "export":
                emit({
                    "schema_version": "skeleton.quest_factions_export_frame.v1",
                    "kind": "export", "bundle": export_factions(current),
                })
            else:
                emit(_frame("checkpoint", current, include_save=True))
                if message["command"] == "quit":
                    return current
            continue
        if set(message) != {"action"} or type(message["action"]) is not dict:
            rejected += 1
            emit(_frame("rejected", current, error="invalid action envelope"))
            if rejected >= MAX_REJECTED_INPUTS:
                raise CombatSessionError("faction play rejected input budget exhausted")
            continue
        action = message["action"]
        if action not in legal:
            rejected += 1
            emit(_frame("rejected", current, error="action not legal in current source state"))
            if rejected >= MAX_REJECTED_INPUTS:
                raise CombatSessionError("faction play rejected input budget exhausted")
            continue
        current = _advance(current, action)
        accepted += 1
        rejected = 0
        emit(_frame(
            "transition", current,
            include_save=(accepted % checkpoint_every == 0),
        ))
    emit(_frame("checkpoint", current, include_save=True))
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-factions-play")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--resume-json")
    parser.add_argument("--source-digest")
    parser.add_argument("--checkpoint-every", type=int, default=8)
    parser.add_argument("--max-turns", type=int, default=MAX_ACTIONS)
    args = parser.parse_args(list(argv))
    try:
        source = (
            original_factions() if args.demo else
            _parse_json(args.source_json, "faction source")
            if args.source_json is not None else None
        )
        saved = (
            _parse_json(args.resume_json, "faction checkpoint")
            if args.resume_json is not None else None
        )
        play_factions(
            source, session=saved, expected_source_digest=args.source_digest,
            checkpoint_every=args.checkpoint_every, max_turns=args.max_turns,
        )
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
