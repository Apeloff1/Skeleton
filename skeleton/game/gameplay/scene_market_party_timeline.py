"""Bounded, replay-proven cooperative market timeline and branch editor.

The journal and economy are owned by the canonical party reducer. Timeline
inspection never rewrites the source, mints currency or trusts event receipts.
Forks are new offline playthroughs, not merges into an authoritative save.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    _advance, export_party, import_party, new_party, original_party,
    resume_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS, _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_timeline.v1"
FORK_SCHEMA = "skeleton.scene_market_party_fork.v1"
MAX_PAGE = 32


def _index(value: Any, count: int, name: str) -> int:
    if type(value) is not int or value < 0 or value > count:
        raise SceneTravelError(f"invalid cooperative {name}")
    return value


def seek_party(checkpoint: Any, sequence: int) -> dict[str, Any]:
    """Rebuild an exact checkpoint at a turn boundary from verified source."""
    original = verify_party(checkpoint)
    _index(sequence, len(original["journal"]), "timeline sequence")
    result = new_party(original["source"])
    for event in original["journal"][:sequence]:
        result = _advance(result, event["turn"])
        if result["journal"][-1] != event:
            raise SceneTravelError("cooperative timeline diverged from source")
    if result["state"]["sequence"] != sequence:
        raise SceneTravelError("cooperative timeline sequence mismatch")
    if import_party(export_party(result)) != result:
        raise SceneTravelError("cooperative timeline checkpoint cannot export")
    return result


def inspect_party_timeline(checkpoint: Any, *, start: int = 0,
                           limit: int = 16) -> dict[str, Any]:
    """Page through real turn receipts with replayed economy consequences."""
    original = verify_party(checkpoint)
    count = len(original["journal"])
    _index(start, count, "timeline start")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise SceneTravelError("invalid cooperative timeline page budget")
    cursor = seek_party(original, start)
    entries = []
    for event in original["journal"][start:start + limit]:
        before = cursor
        cursor = _advance(cursor, event["turn"])
        if cursor["journal"][-1] != event:
            raise SceneTravelError("cooperative timeline event mismatch")
        previous = before["state"]["market"]["state"]
        current = cursor["state"]["market"]["state"]
        keys = sorted(set(previous["goods"]) | set(current["goods"]))
        goods_delta = {key: current["goods"].get(key, 0) -
                       previous["goods"].get(key, 0) for key in keys}
        goods_delta = {key: value for key, value in goods_delta.items() if value}
        entries.append({
            "sequence": event["sequence"],
            "player_id": event["turn"]["player_id"],
            "action": event["turn"]["action"],
            "event_receipt": event["receipt"],
            "before_state_digest": before["state_digest"],
            "after_state_digest": cursor["state_digest"],
            "save_digest": dig(cursor["save"]),
            "market_before": event["market_before"],
            "market_after": event["market_after"],
            "credits_delta": current["credits"] - previous["credits"],
            "goods_delta": goods_delta,
            "phase": current["phase"],
            "round": cursor["state"]["round"],
        })
    portable = export_party(cursor)
    result = {
        "schema_version": SCHEMA,
        "source_digest": original["source_digest"],
        "original_state_digest": original["state_digest"],
        "original_turn_count": count,
        "start": start, "limit": limit, "next_sequence": start + len(entries),
        "has_more": start + len(entries) < count,
        "entries": entries,
        "page_terminal_state_digest": cursor["state_digest"],
        "page_terminal_save_digest": dig(cursor["save"]),
        "page_terminal_export_checksum": portable["checksum"],
        "qualification": "canonical_replay_not_actor_authentication",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_party_timeline(checkpoint: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid cooperative timeline report")
    expected = inspect_party_timeline(
        checkpoint, start=report.get("start"), limit=report.get("limit"))
    if expected != report:
        raise SceneTravelError("cooperative timeline report was altered")
    return expected


def fork_party(checkpoint: Any, sequence: int,
               turns: Any) -> dict[str, Any]:
    """Create a distinct, portable playthrough from an exact earlier turn."""
    original = verify_party(checkpoint)
    _index(sequence, len(original["journal"]), "fork sequence")
    if (type(turns) is not list or
            len(turns) + sequence > MAX_STEPS):
        raise SceneTravelError("invalid cooperative fork turn batch")
    prefix = seek_party(original, sequence)
    branch = resume_party(prefix, turns)
    portable = export_party(branch)
    if import_party(json.loads(json.dumps(portable))) != branch:
        raise SceneTravelError("cooperative fork export did not round trip")
    result = {
        "schema_version": FORK_SCHEMA,
        "source_digest": original["source_digest"],
        "parent_state_digest": original["state_digest"],
        "prefix_sequence": sequence,
        "prefix_state_digest": prefix["state_digest"],
        "fork_state_digest": branch["state_digest"],
        "fork_save_digest": dig(branch["save"]),
        "fork_phase": branch["state"]["market"]["state"]["phase"],
        "turns": copy.deepcopy(turns),
        "turn_count": len(turns),
        "portable": portable,
        "qualification": "offline_fork_not_authoritative_save_merge",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_party_fork(checkpoint: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid cooperative fork report")
    expected = fork_party(checkpoint, report.get("prefix_sequence"),
                          report.get("turns"))
    if expected != report:
        raise SceneTravelError("cooperative fork report was altered")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-market-party-timeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    page = sub.add_parser("page")
    page.add_argument("--session-json", required=True)
    page.add_argument("--start", type=int, default=0)
    page.add_argument("--limit", type=int, default=16)
    seek = sub.add_parser("seek")
    seek.add_argument("--session-json", required=True)
    seek.add_argument("--sequence", type=int, required=True)
    fork = sub.add_parser("fork")
    fork.add_argument("--session-json", required=True)
    fork.add_argument("--sequence", type=int, required=True)
    fork.add_argument("--turns-json", required=True)
    verify_page = sub.add_parser("verify-page")
    verify_page.add_argument("--session-json", required=True)
    verify_page.add_argument("--report-json", required=True)
    verify_fork = sub.add_parser("verify-fork")
    verify_fork.add_argument("--session-json", required=True)
    verify_fork.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, turns = original_party()
            original = simulate_party(source, turns)
            result = fork_party(original, len(turns) // 2,
                                turns[len(turns) // 2:])
            verify_party_fork(original, result)
        elif args.command == "page":
            result = inspect_party_timeline(
                _json(args.session_json), start=args.start, limit=args.limit)
        elif args.command == "seek":
            result = seek_party(_json(args.session_json), args.sequence)
        elif args.command == "fork":
            result = fork_party(_json(args.session_json), args.sequence,
                                _json(args.turns_json))
        elif args.command == "verify-page":
            result = verify_party_timeline(
                _json(args.session_json), _json(args.report_json))
        else:
            result = verify_party_fork(
                _json(args.session_json), _json(args.report_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
