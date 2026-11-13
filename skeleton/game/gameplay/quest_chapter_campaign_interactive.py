"""Interactive, resumable chapter campaign over the canonical quest engine.

Player input is a request, never an authoritative state transition. Every
accepted quest move and chapter advancement is replayed through the authored
campaign, with bounded input, explicit checkpoints and portable final saves.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import MAX_BYTES, MAX_SOURCE_BYTES
from skeleton.game.gameplay.expedition_quest_interactive import (
    legal_quest_actions, parse_quest_action,
)
from skeleton.game.gameplay.quest_chapter_campaign import (
    MAX_ACTIONS, _step, export_campaign, import_campaign, new_campaign,
    original_campaign, verify_campaign,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json,
)

MAX_INPUT_BYTES = 128 * 1024
MAX_RETRIES = 3
MAX_CHECKPOINT_INTERVAL = 64


def parse_campaign_action(line: str) -> dict[str, Any]:
    if type(line) is not str:
        raise CombatSessionError("campaign input must be text")
    try:
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise CombatSessionError("campaign input exceeds byte budget")
    except UnicodeError as exc:
        raise CombatSessionError("invalid campaign input encoding") from exc
    raw = line.strip()
    if raw == "advance":
        return {"kind": "advance"}
    if raw.startswith("{"):
        obj = _parse_json(raw, "campaign action")
        if type(obj) is not dict:
            raise CombatSessionError("campaign JSON action must be object")
        if obj.get("kind") == "advance":
            if set(obj) != {"kind"}:
                raise CombatSessionError("invalid advance action fields")
            return {"kind": "advance"}
        if obj.get("kind") == "quest":
            if set(obj) != {"kind", "action"}:
                raise CombatSessionError("invalid quest action fields")
            return {"kind": "quest", "action": obj["action"]}
        raise CombatSessionError("unsupported campaign JSON action")
    return {"kind": "quest", "action": parse_quest_action(raw)}


def legal_campaign_actions(payload: Any) -> list[dict[str, Any]]:
    current = verify_campaign(payload)
    state = current["state"]
    if state["phase"] != "active" or state["tick"] >= MAX_ACTIONS:
        return []
    quest = state["active_quest"]
    candidates = (
        [{"kind": "quest", "action": action}
         for action in legal_quest_actions(quest)]
        if quest["state"]["phase"] == "active"
        else [{"kind": "advance"}]
    )
    available = []
    for action in candidates:
        try:
            _step(current, action)
        except CombatSessionError:
            continue
        available.append(action)
    return available


def _emit(writer: Any, event: dict[str, Any]) -> None:
    try:
        raw = json.dumps(event, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=False)
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise CombatSessionError("campaign output byte budget exceeded")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid campaign output") from exc
    writer.write(raw + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    saved = verify_campaign(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"], "session": saved,
    })


def play_campaign(source: Any = None, *, session: Any = None,
                  expected_source_digest: str | None = None,
                  checkpoint_every: int = 8, max_turns: int = 96,
                  input_stream: Any = None, output_stream: Any = None) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one campaign source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL:
        raise CombatSessionError("invalid campaign checkpoint interval")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_ACTIONS:
        raise CombatSessionError("invalid campaign turn budget")
    current = new_campaign(source) if session is None else verify_campaign(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or expected_source_digest != current["source_digest"]):
            raise CombatSessionError("campaign source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    initial_tick = current["state"]["tick"]
    _emit(writer, {
        "event": "started", "tick": initial_tick,
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
    })
    while current["state"]["phase"] == "active":
        if current["state"]["tick"] - initial_tick >= max_turns:
            _checkpoint(writer, current, "turn_budget")
            raise CombatSessionError("campaign turn budget exhausted; checkpoint emitted")
        state = current["state"]
        chapter = current["source"]["chapters"][state["chapter_index"]]
        quest = state["active_quest"]
        available = legal_campaign_actions(current)
        _emit(writer, {
            "event": "prompt", "tick": state["tick"],
            "chapter_id": chapter["id"],
            "required_ending": chapter["required_ending"],
            "chapter_index": state["chapter_index"],
            "earned_flags": state["flags"],
            "location": quest["state"]["location"],
            "items": quest["state"]["items"],
            "quest_phase": quest["state"]["phase"],
            "quest_ending": quest["state"]["ending"],
            "available_actions": available,
            "state_digest": current["state_digest"],
        })
        if not available:
            _checkpoint(writer, current, "no_legal_action")
            raise CombatSessionError("no legal campaign action; checkpoint emitted")
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise CombatSessionError("campaign input ended; checkpoint emitted")
            try:
                action = parse_campaign_action(line)
                if action not in available:
                    raise CombatSessionError("campaign action not currently available")
                advanced = _step(current, action)
            except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
                _emit(writer, {
                    "event": "invalid", "attempt": attempt + 1, "error": str(exc),
                })
                if attempt + 1 == MAX_RETRIES:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise CombatSessionError(
                        "campaign input retries exhausted; checkpoint emitted"
                    ) from exc
                continue
            current = advanced
            _emit(writer, {
                "event": "accepted", "tick": current["state"]["tick"],
                "state_digest": current["state_digest"],
                "action_receipt": current["journal"][-1]["receipt"],
            })
            if current["state"]["tick"] % checkpoint_every == 0:
                _checkpoint(writer, current, "interval")
            break
    final = verify_campaign(current)
    bundle = export_campaign(final)
    if import_campaign(bundle) != final:
        raise CombatSessionError("campaign portable terminal replay mismatch")
    _checkpoint(writer, final, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": final["state"]["phase"],
        "earned_flags": final["state"]["flags"],
        "state_digest": final["state_digest"], "bundle": bundle,
    })
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-campaign-play")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--resume-json")
    parser.add_argument("--source-digest")
    parser.add_argument("--checkpoint-every", type=int, default=8)
    parser.add_argument("--max-turns", type=int, default=96)
    args = parser.parse_args(list(argv))
    try:
        saved = (
            _parse_json(args.resume_json, "campaign save")
            if args.resume_json is not None else None
        )
        source = original_campaign() if args.demo else (
            _parse_json(args.source_json, "campaign source")
            if args.source_json is not None else None
        )
        play_campaign(
            source, session=saved, expected_source_digest=args.source_digest,
            checkpoint_every=args.checkpoint_every, max_turns=args.max_turns,
        )
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
