"""Playable human combat campaign acceptance with verified decisions and exports."""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_decision_board import decision_board
from skeleton.game.gameplay.combat_campaign_player import (
    _bounded, demo_player_campaign, export_player_campaign,
    import_player_campaign, new_player_campaign, play_player_campaign,
    resume_player_campaign, simulate_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _parse_json

SCHEMA = "skeleton.combat_player_acceptance.v1"
MAX_ACCEPT_ACTIONS = 32
MAX_SOURCE_BYTES = 64 * 1024
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024


class _BoundedWriter:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.bytes_written = 0

    def write(self, value: str) -> int:
        if type(value) is not str:
            raise CombatSessionError("non-text campaign transcript")
        size = len(value.encode("utf-8"))
        if self.bytes_written + size > MAX_TRANSCRIPT_BYTES:
            raise CombatSessionError("campaign transcript exceeds acceptance budget")
        self.parts.append(value)
        self.bytes_written += size
        return len(value)

    def flush(self) -> None:
        pass

    def events(self) -> list[dict[str, Any]]:
        return [
            _parse_json(line, "campaign event")
            for line in "".join(self.parts).splitlines()
        ]


def accept_player_campaign(source: Any, actions: Any) -> dict[str, Any]:
    """Require a won campaign with identical board, CLI, restart and export."""
    _bounded(source)
    source_bytes = len(json.dumps(source, sort_keys=True, allow_nan=False,
                                  separators=(",", ":")).encode("utf-8"))
    if source_bytes > MAX_SOURCE_BYTES:
        raise CombatSessionError("campaign acceptance source exceeds budget")
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACCEPT_ACTIONS:
        raise CombatSessionError("invalid campaign acceptance action budget")
    _bounded(actions)
    initial = new_player_campaign(source)
    cursor = initial
    board_receipts = []
    for action in actions:
        board = decision_board(cursor)
        preview = next((choice for choice in board["choices"]
                        if choice["action"] == action), None)
        if preview is None:
            raise CombatSessionError("campaign action absent from canonical board")
        cursor = resume_player_campaign(cursor, [action])
        if cursor["state_digest"] != preview["state_digest"]:
            raise CombatSessionError("campaign decision preview replay mismatch")
        board_receipts.append(board["checksum"])
    final = simulate_player_campaign(source, actions)
    if cursor != final or final["state"]["phase"] != "won":
        raise CombatSessionError("campaign acceptance requires replayable victory")
    if verify_player_campaign(final) != final:
        raise CombatSessionError("campaign acceptance replay mismatch")
    mid = len(actions) // 2
    restarted = resume_player_campaign(
        simulate_player_campaign(source, actions[:mid]), actions[mid:])
    if restarted != final:
        raise CombatSessionError("campaign acceptance checkpoint mismatch")
    portable = export_player_campaign(final)
    if import_player_campaign(portable) != final:
        raise CombatSessionError("campaign acceptance portable mismatch")
    transcript = _BoundedWriter()
    encoded = [json.dumps(action, sort_keys=True, separators=(",", ":"))
               for action in actions]
    played = play_player_campaign(
        source=source, reader=io.StringIO("\n".join(encoded) + "\n"),
        writer=transcript)
    events = transcript.events()
    checkpoints = [event for event in events if event.get("event") == "checkpoint"]
    terminals = [event for event in events if event.get("event") == "terminal"]
    if (played != final or len(checkpoints) != len(actions)
            or len(terminals) != 1
            or terminals[0]["state_digest"] != final["state_digest"]
            or verify_player_campaign(checkpoints[-1]["session"]) != final):
        raise CombatSessionError("campaign interactive play disagrees with replay")
    result = {
        "schema_version": SCHEMA,
        "status": "playable_verified",
        "source_digest": final["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "final_state_digest": final["state_digest"],
        "hero_hp": final["state"]["hero_hp"],
        "earned_currency": final["state"]["currency"],
        "actions": actions, "action_count": len(actions),
        "board_receipt_digest": dig(board_receipts),
        "journal_digest": dig(final["journal"]),
        "interactive_event_digest": dig(events),
        "portable_checksum": portable["checksum"],
        "proof_kind": "canonical_playable_acceptance_not_signature",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_player_acceptance(receipt: Any, source: Any) -> dict[str, Any]:
    _bounded(receipt)
    if type(receipt) is not dict or set(receipt) != {
        "schema_version", "status", "source_digest", "initial_state_digest",
        "final_state_digest", "hero_hp", "earned_currency", "actions",
        "action_count", "board_receipt_digest", "journal_digest",
        "interactive_event_digest", "portable_checksum", "proof_kind",
        "checksum",
    } or receipt["schema_version"] != SCHEMA or receipt["status"] != "playable_verified":
        raise CombatSessionError("invalid campaign acceptance receipt")
    if receipt["checksum"] != dig({k: v for k, v in receipt.items()
                                  if k != "checksum"}):
        raise CombatSessionError("campaign acceptance checksum mismatch")
    expected = accept_player_campaign(source, receipt["actions"])
    if expected != receipt:
        raise CombatSessionError("campaign acceptance source or replay mismatch")
    return expected


def original_player_acceptance() -> dict[str, Any]:
    demo = demo_player_campaign()
    return accept_player_campaign(
        original_campaign(), [event["action"] for event in demo["journal"]])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("accept")
    p.add_argument("--source-json", required=True)
    p.add_argument("--actions-json", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--source-json", required=True)
    p.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_player_acceptance()
        elif args.command == "accept":
            result = accept_player_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.actions_json, "campaign actions"))
        else:
            result = verify_player_acceptance(
                _parse_json(args.receipt_json, "acceptance receipt"),
                _parse_json(args.source_json, "campaign source"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
