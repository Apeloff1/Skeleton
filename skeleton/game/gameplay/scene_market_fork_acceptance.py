"""End-to-end delivery certification for an authored, won market fork.

Proves source -> checkpoint -> player choice -> canonical market replay ->
ledger conservation -> portable game export/import. This is an offline
functional acceptance witness, never device or security certification.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _bounded, _json, export_market, import_market, verify_market,
)
from skeleton.game.gameplay.scene_market_fork import (
    choose_market_fork, export_market_fork, import_market_fork,
    original_fork, verify_market_fork,
)
from skeleton.game.gameplay.scene_market_ledger import (
    audit_market_ledger, verify_market_ledger,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_fork_acceptance.v1"


def accept_market_fork(report: Any, candidate_id: str) -> dict[str, Any]:
    """Produce a fully replayable player-selected delivery witness."""
    preview = verify_market_fork(report)
    name = _id(candidate_id, "accepted candidate")
    selected = choose_market_fork(preview, name)
    if selected["state"]["phase"] != "won":
        raise SceneTravelError("fork acceptance requires completed market victory")
    package = export_market(selected)
    if import_market(package) != selected:
        raise SceneTravelError("fork package round-trip mismatch")
    preview_bundle = export_market_fork(preview)
    if import_market_fork(preview_bundle) != preview:
        raise SceneTravelError("fork preview round-trip mismatch")
    ledger = audit_market_ledger(selected)
    verify_market_ledger(selected, ledger)
    result = {
        "schema_version": SCHEMA,
        "source_digest": selected["source_digest"],
        "checkpoint_state_digest": preview["checkpoint_state_digest"],
        "candidate_id": name,
        "preview_bundle": preview_bundle,
        "selected_game_bundle": package,
        "ledger": ledger,
        "ending": "won",
        "qualification": "offline_gameplay_replay_only_not_device_release",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_market_fork_acceptance(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "checkpoint_state_digest",
        "candidate_id", "preview_bundle", "selected_game_bundle",
        "ledger", "ending", "qualification", "checksum",
    }, "fork acceptance witness")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported fork acceptance schema")
    preview = import_market_fork(obj["preview_bundle"])
    expected = accept_market_fork(preview, obj["candidate_id"])
    if obj != expected:
        raise SceneTravelError("fork delivery witness mismatch")
    selected = import_market(obj["selected_game_bundle"])
    if verify_market(selected) != selected:
        raise SceneTravelError("fork selected game replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-fork-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    accept = sub.add_parser("accept")
    accept.add_argument("--report-json", required=True)
    accept.add_argument("--candidate-id", required=True)
    sub.add_parser("verify").add_argument("--witness-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = accept_market_fork(original_fork(), "complete_delivery")
        elif args.command == "accept":
            result = accept_market_fork(
                _json(args.report_json), args.candidate_id,
            )
        else:
            result = verify_market_fork_acceptance(_json(args.witness_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
