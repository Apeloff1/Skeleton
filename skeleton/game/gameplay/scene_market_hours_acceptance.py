"""Exact-source merchant gameplay acceptance: replay, economy, board and export."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, _json
from skeleton.game.gameplay.scene_market_hours import (
    edit_hours, export_hours, import_hours, merchant_board,
    normalize_hours, verify_hours, verify_merchant_board,
)
from skeleton.game.gameplay.scene_market_ledger import audit_market_ledger
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_hours_acceptance.v1"


def accept_hours(payload: Any, *, require_victory: bool = True,
                 include_editor: bool = True) -> dict[str, Any]:
    if type(require_victory) is not bool or type(include_editor) is not bool:
        raise SceneTravelError("invalid merchant acceptance flags")
    session = verify_hours(payload)
    if require_victory and session["state"]["phase"] != "won":
        raise SceneTravelError("merchant campaign victory not proven")
    market = session["state"]["market"]
    report = audit_market_ledger(market)
    if (report["credits_remaining"] != market["state"]["credits"]
            or report["reputation_earned"] != market["state"]["reputation"]
            or report["journal_length"] != len(session["journal"])):
        raise SceneTravelError("merchant economy replay mismatch")
    board = merchant_board(session)
    verify_merchant_board(session, board)
    bundle = export_hours(session)
    if import_hours(bundle) != session:
        raise SceneTravelError("merchant portable save round trip mismatch")
    source = normalize_hours(session["source"])
    if include_editor:
        # A transactional no-op edit of the first window must preserve source.
        first = source["windows"][0]
        edited = edit_hours(source, [
            {"kind": "remove", "market_id": first["market_id"],
             "opens_at": first["opens_at"]},
            {"kind": "add", **first},
        ])
        if edited != source:
            raise SceneTravelError("merchant authoring round trip mismatch")
    result = {
        "schema_version": SCHEMA,
        "status": "accepted_offline_witness"
        if session["state"]["phase"] == "won" else "incomplete",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
        "journal_length": len(session["journal"]),
        "market_ledger_checksum": report["checksum"],
        "board_checksum": board["checksum"],
        "portable_checksum": bundle["checksum"],
        "merchant_purchases": session["state"]["purchases_by_merchant"],
        "phase": session["state"]["phase"],
        "include_editor": include_editor,
        "require_victory": require_victory,
        "qualification": "one_offline_replay_not_device_release",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_hours_acceptance(session: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid merchant acceptance witness")
    expected = accept_hours(
        session, require_victory=report.get("require_victory"),
        include_editor=report.get("include_editor"),
    )
    if report != expected:
        raise SceneTravelError("merchant acceptance witness mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-hours-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--session-json", required=True)
    audit.add_argument("--allow-incomplete", action="store_true")
    audit.add_argument("--skip-editor", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "audit":
            result = accept_hours(
                _json(args.session_json),
                require_victory=not args.allow_incomplete,
                include_editor=not args.skip_editor,
            )
        else:
            result = verify_hours_acceptance(
                _json(args.session_json), _json(args.report_json),
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
