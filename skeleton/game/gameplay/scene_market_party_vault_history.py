"""Replay-verified revision history and recovery for cooperative market save slots.

This is an offline recovery surface, not a mutable history editor or an
authentication system. Every snapshot is reconstructed by replaying the
canonical vault's original event log, and a restore is a NEW leased event.
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
    export_party, import_party, original_party, resume_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_vault import (
    _apply, export_vault, import_vault, new_vault, read_slot, transact_vault,
    verify_vault,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id

HISTORY_SCHEMA = "skeleton.scene_market_party_vault_history.v1"
DIFF_SCHEMA = "skeleton.scene_market_party_vault_diff.v1"
RECOVERY_SCHEMA = "skeleton.scene_market_party_vault_recovery.v1"
MAX_PAGE = 16


def _revision(value: Any, current: int, label: str) -> int:
    if type(value) is not int or value < 0 or value > current:
        raise SceneTravelError(f"invalid cooperative vault {label}")
    return value


def _slot_name(value: Any) -> str:
    name = _id(value, "vault slot")
    if len(name) > 40:
        raise SceneTravelError("cooperative vault slot too long")
    return name


def _slot_digest(slots: dict[str, Any], slot: str) -> str | None:
    value = slots.get(slot)
    return value["state_digest"] if value is not None else None


def seek_vault(raw: Any, revision: int) -> dict[str, Any]:
    """Reconstruct a historic revision; never trust a serialized snapshot."""
    verified = verify_vault(raw)
    _revision(revision, verified["revision"], "seek revision")
    cursor = new_vault(verified["source"])
    for event in verified["journal"][:revision]:
        cursor = _apply(cursor, event["action"])
        if cursor["journal"][-1] != event:
            raise SceneTravelError("cooperative vault historical event diverged")
    if cursor["revision"] != revision:
        raise SceneTravelError("cooperative vault historical revision mismatch")
    if import_vault(export_vault(cursor)) != cursor:
        raise SceneTravelError("cooperative vault historical export diverged")
    return cursor


def history_vault(raw: Any, *, start: int = 0,
                  limit: int = 8) -> dict[str, Any]:
    """Page immutable event receipts with replayed before/after slot leases."""
    verified = verify_vault(raw)
    _revision(start, verified["revision"], "history start")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise SceneTravelError("invalid cooperative vault history page budget")
    cursor = seek_vault(verified, start)
    entries: list[dict[str, Any]] = []
    for event in verified["journal"][start:start + limit]:
        before = cursor
        cursor = _apply(cursor, event["action"])
        if cursor["journal"][-1] != event:
            raise SceneTravelError("cooperative vault history receipt mismatch")
        slot = event["action"]["slot"]
        entries.append({
            "sequence": event["sequence"],
            "revision": cursor["revision"],
            "kind": event["action"]["kind"],
            "slot": slot,
            "before_slot_digest": _slot_digest(before["slots"], slot),
            "after_slot_digest": _slot_digest(cursor["slots"], slot),
            "before_state_digest": before["state_digest"],
            "after_state_digest": cursor["state_digest"],
            "event_receipt": event["receipt"],
        })
    result = {
        "schema_version": HISTORY_SCHEMA,
        "source_digest": verified["source_digest"],
        "current_state_digest": verified["state_digest"],
        "current_revision": verified["revision"],
        "start": start,
        "limit": limit,
        "next_revision": start + len(entries),
        "has_more": start + len(entries) < verified["revision"],
        "entries": entries,
        "page_terminal_state_digest": cursor["state_digest"],
        "page_terminal_export_checksum": export_vault(cursor)["checksum"],
        "qualification": "replayed_offline_history_not_actor_authentication",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_history_vault(raw: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid cooperative vault history report")
    expected = history_vault(
        raw, start=report.get("start"), limit=report.get("limit"))
    if expected != report:
        raise SceneTravelError("cooperative vault history report altered")
    return expected


def diff_vault(raw: Any, from_revision: int,
               to_revision: int) -> dict[str, Any]:
    """Show source-bound slot differences without leaking checkpoint payloads."""
    verified = verify_vault(raw)
    first = seek_vault(verified, _revision(
        from_revision, verified["revision"], "from revision"))
    second = seek_vault(verified, _revision(
        to_revision, verified["revision"], "to revision"))
    changes = []
    for name in sorted(set(first["slots"]) | set(second["slots"])):
        before = _slot_digest(first["slots"], name)
        after = _slot_digest(second["slots"], name)
        if before != after:
            changes.append({
                "slot": name, "before_slot_digest": before,
                "after_slot_digest": after,
                "before_turns": (len(first["slots"][name]["journal"])
                                 if name in first["slots"] else None),
                "after_turns": (len(second["slots"][name]["journal"])
                                if name in second["slots"] else None),
            })
    result = {
        "schema_version": DIFF_SCHEMA,
        "source_digest": verified["source_digest"],
        "current_state_digest": verified["state_digest"],
        "from_revision": first["revision"],
        "to_revision": second["revision"],
        "from_state_digest": first["state_digest"],
        "to_state_digest": second["state_digest"],
        "changes": changes,
        "qualification": "offline_revision_comparison_not_save_merge",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def preview_recovery(raw: Any, *, target_revision: int, slot: str,
                     expected_revision: int) -> dict[str, Any]:
    """Prove the exact CAS action required to restore a historic slot."""
    verified = verify_vault(raw)
    _revision(expected_revision, verified["revision"], "expected revision")
    if expected_revision != verified["revision"]:
        raise SceneTravelError("stale cooperative vault recovery revision")
    target = seek_vault(verified, _revision(
        target_revision, verified["revision"], "target revision"))
    name = _slot_name(slot)
    previous = _slot_digest(verified["slots"], name)
    desired = _slot_digest(target["slots"], name)
    if previous == desired:
        raise SceneTravelError("cooperative vault recovery would not change slot")
    action: dict[str, Any] = {
        "kind": "put" if desired is not None else "delete",
        "slot": name,
        "expected_revision": expected_revision,
        "expected_slot_digest": previous,
    }
    if desired is not None:
        action["checkpoint"] = copy.deepcopy(target["slots"][name])
    result_vault = transact_vault(verified, action)
    if _slot_digest(result_vault["slots"], name) != desired:
        raise SceneTravelError("cooperative vault recovery result diverged")
    portable = export_vault(result_vault)
    if import_vault(json.loads(json.dumps(portable))) != result_vault:
        raise SceneTravelError("cooperative vault recovery export diverged")
    report = {
        "schema_version": RECOVERY_SCHEMA,
        "source_digest": verified["source_digest"],
        "parent_state_digest": verified["state_digest"],
        "parent_revision": verified["revision"],
        "target_revision": target_revision,
        "target_state_digest": target["state_digest"],
        "slot": name,
        "before_slot_digest": previous,
        "after_slot_digest": desired,
        "action": action,
        "result_revision": result_vault["revision"],
        "result_state_digest": result_vault["state_digest"],
        "result_export_checksum": portable["checksum"],
        "qualification": "new_cas_event_not_history_rewrite_or_authentication",
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_recovery(raw: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid cooperative vault recovery report")
    expected = preview_recovery(
        raw, target_revision=report.get("target_revision"),
        slot=report.get("slot"), expected_revision=report.get("parent_revision"))
    if expected != report:
        raise SceneTravelError("cooperative vault recovery report altered")
    return expected


def apply_recovery(raw: Any, report: Any) -> dict[str, Any]:
    """Commit a verified preview as one new event, never overwrite history."""
    verified = verify_vault(raw)
    approved = verify_recovery(verified, report)
    updated = transact_vault(verified, approved["action"])
    if (updated["revision"] != approved["result_revision"]
            or updated["state_digest"] != approved["result_state_digest"]
            or export_vault(updated)["checksum"] != approved["result_export_checksum"]):
        raise SceneTravelError("cooperative vault recovery publication diverged")
    return updated


def accept_recovery() -> dict[str, Any]:
    """End-to-end played campaign, rollback, resume, replay and export proof."""
    source, turns = original_party()
    cut = len(turns) // 2
    first = simulate_party(source, turns[:cut])
    completed = simulate_party(source, turns)
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": first})
    vault = transact_vault(vault, {
        "kind": "put", "slot": "campaign", "expected_revision": 1,
        "expected_slot_digest": first["state_digest"], "checkpoint": completed})
    before = copy.deepcopy(vault)
    preview = preview_recovery(
        vault, target_revision=1, slot="campaign", expected_revision=2)
    if verify_recovery(vault, json.loads(json.dumps(preview))) != preview:
        raise SceneTravelError("cooperative recovery preview failed replay")
    restored = apply_recovery(vault, preview)
    if vault != before or read_slot(restored, "campaign") != first:
        raise SceneTravelError("cooperative recovery altered parent or checkpoint")
    resumed = resume_party(read_slot(restored, "campaign"), turns[cut:])
    if resumed != completed or import_party(export_party(resumed)) != completed:
        raise SceneTravelError("cooperative recovery campaign replay diverged")
    portable = export_vault(restored)
    if import_vault(json.loads(json.dumps(portable))) != restored:
        raise SceneTravelError("cooperative recovery portable vault diverged")
    page = history_vault(restored, start=0, limit=MAX_PAGE)
    if verify_history_vault(restored, page) != page:
        raise SceneTravelError("cooperative recovery history failed replay")
    result = {
        "schema_version": "skeleton.scene_market_party_vault_recovery_acceptance.v1",
        "source_digest": restored["source_digest"],
        "parent_state_digest": before["state_digest"],
        "restored_state_digest": restored["state_digest"],
        "earned_campaign_digest": completed["state_digest"],
        "restored_checkpoint_digest": first["state_digest"],
        "revision": restored["revision"],
        "turns": len(turns),
        "phase": completed["state"]["market"]["state"]["phase"],
        "export_checksum": portable["checksum"],
        "qualification": "offline_replay_not_actor_authentication",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-market-party-vault-history")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accept")
    seek = sub.add_parser("seek")
    seek.add_argument("--vault-json", required=True)
    seek.add_argument("--revision", required=True, type=int)
    history = sub.add_parser("history")
    history.add_argument("--vault-json", required=True)
    history.add_argument("--start", type=int, default=0)
    history.add_argument("--limit", type=int, default=8)
    diff = sub.add_parser("diff")
    diff.add_argument("--vault-json", required=True)
    diff.add_argument("--from-revision", type=int, required=True)
    diff.add_argument("--to-revision", type=int, required=True)
    for command in ("preview", "apply"):
        p = sub.add_parser(command)
        p.add_argument("--vault-json", required=True)
        if command == "preview":
            p.add_argument("--target-revision", type=int, required=True)
            p.add_argument("--slot", required=True)
            p.add_argument("--expected-revision", type=int, required=True)
        else:
            p.add_argument("--report-json", required=True)
    for command in ("verify-history", "verify-preview"):
        p = sub.add_parser(command)
        p.add_argument("--vault-json", required=True)
        p.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "accept":
            result = accept_recovery()
        else:
            vault = _json(args.vault_json)
            if args.command == "seek":
                result = seek_vault(vault, args.revision)
            elif args.command == "history":
                result = history_vault(vault, start=args.start, limit=args.limit)
            elif args.command == "diff":
                result = diff_vault(vault, args.from_revision, args.to_revision)
            elif args.command == "preview":
                result = preview_recovery(
                    vault, target_revision=args.target_revision,
                    slot=args.slot, expected_revision=args.expected_revision)
            elif args.command == "apply":
                result = apply_recovery(vault, _json(args.report_json))
            elif args.command == "verify-history":
                result = verify_history_vault(vault, _json(args.report_json))
            else:
                result = verify_recovery(vault, _json(args.report_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
