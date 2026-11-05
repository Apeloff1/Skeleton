"""Deterministic cooperative playthrough comparison and safe branch selection.

Never merges two saves or awards resources. It replays both source-bound
checkpoints, proves the common journal prefix, exposes earned consequences
and exports only the explicitly selected canonical branch.
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
    export_party, import_party, original_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_market_party_timeline import seek_party
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_compare.v1"
SELECTION = "skeleton.scene_market_party_selection.v1"
MAX_BYTES = 2 * 1024 * 1024


def _limit(payload: Any) -> None:
    _bounded(payload, MAX_BYTES)


def _metrics(session: dict[str, Any]) -> dict[str, Any]:
    market = session["state"]["market"]["state"]
    return {"phase": market["phase"], "credits": market["credits"],
            "goods": copy.deepcopy(market["goods"]),
            "sequence": session["state"]["sequence"],
            "round": session["state"]["round"],
            "contributions": copy.deepcopy(session["state"]["contributions"]),
            "passes": copy.deepcopy(session["state"]["passes"])}


def compare_party(left: Any, right: Any) -> dict[str, Any]:
    a, b = verify_party(left), verify_party(right)
    if a["source_digest"] != b["source_digest"]:
        raise SceneTravelError("cooperative comparison source mismatch")
    if import_party(export_party(a)) != a or import_party(export_party(b)) != b:
        raise SceneTravelError("cooperative comparison portable replay mismatch")
    prefix = 0
    for ea, eb in zip(a["journal"], b["journal"]):
        if ea != eb:
            break
        prefix += 1
    common = seek_party(a, prefix)
    if seek_party(b, prefix) != common:
        raise SceneTravelError("cooperative comparison common prefix diverged")
    left_metrics, right_metrics = _metrics(a), _metrics(b)
    goods = sorted(set(left_metrics["goods"]) | set(right_metrics["goods"]))
    delta = {name: left_metrics["goods"].get(name, 0)
             - right_metrics["goods"].get(name, 0) for name in goods}
    result = {"schema_version": SCHEMA,
              "source_digest": a["source_digest"],
              "left_state_digest": a["state_digest"],
              "right_state_digest": b["state_digest"],
              "common_prefix_turns": prefix,
              "common_prefix_state_digest": common["state_digest"],
              "diverged": prefix < min(len(a["journal"]), len(b["journal"])),
              "left_remaining_turns": len(a["journal"]) - prefix,
              "right_remaining_turns": len(b["journal"]) - prefix,
              "first_left_turn": (copy.deepcopy(a["journal"][prefix]["turn"])
                                  if prefix < len(a["journal"]) else None),
              "first_right_turn": (copy.deepcopy(b["journal"][prefix]["turn"])
                                   if prefix < len(b["journal"]) else None),
              "left": left_metrics, "right": right_metrics,
              "left_minus_right_credits": left_metrics["credits"] - right_metrics["credits"],
              "left_minus_right_goods": delta,
              "qualification": "offline_branch_comparison_not_save_merge"}
    result["checksum"] = dig(result)
    _limit(result)
    return result


def verify_comparison(left: Any, right: Any, report: Any) -> dict[str, Any]:
    _limit(report)
    expected = compare_party(left, right)
    if type(report) is not dict or report != expected:
        raise SceneTravelError("cooperative comparison receipt altered")
    return expected


def select_party(left: Any, right: Any, choice: str,
                 *, expected_left_digest: str,
                 expected_right_digest: str) -> dict[str, Any]:
    report = compare_party(left, right)
    if (expected_left_digest != report["left_state_digest"]
            or expected_right_digest != report["right_state_digest"]):
        raise SceneTravelError("stale cooperative branch selection lease")
    if choice not in ("left", "right"):
        raise SceneTravelError("invalid cooperative branch selection")
    chosen = verify_party(left if choice == "left" else right)
    portable = export_party(chosen)
    if import_party(json.loads(json.dumps(portable))) != chosen:
        raise SceneTravelError("cooperative branch selection export mismatch")
    result = {"schema_version": SELECTION,
              "source_digest": report["source_digest"],
              "comparison_checksum": report["checksum"],
              "choice": choice, "selected_state_digest": chosen["state_digest"],
              "selected_save_digest": dig(chosen["save"]),
              "portable": portable,
              "qualification": "explicit_offline_selection_not_merge_or_authentication"}
    result["checksum"] = dig(result)
    _limit(result)
    return result


def verify_selection(left: Any, right: Any, selection: Any) -> dict[str, Any]:
    _limit(selection)
    if type(selection) is not dict:
        raise SceneTravelError("invalid cooperative branch selection")
    report = compare_party(left, right)
    expected = select_party(left, right, selection.get("choice"),
                            expected_left_digest=report["left_state_digest"],
                            expected_right_digest=report["right_state_digest"])
    if selection != expected:
        raise SceneTravelError("cooperative branch selection receipt altered")
    return expected


def accept_comparison() -> dict[str, Any]:
    source, turns = original_party()
    won = simulate_party(source, turns)
    alternative = simulate_party(source, [
        {"player_id": source["players"][0]["player_id"],
         "action": {"kind": "pass"}}])
    report = compare_party(won, alternative)
    verify_comparison(won, alternative, report)
    selected = select_party(won, alternative, "left",
                            expected_left_digest=won["state_digest"],
                            expected_right_digest=alternative["state_digest"])
    verify_selection(won, alternative, selected)
    if (import_party(selected["portable"]) != won
            or report["left"]["phase"] != "won"
            or report["right"]["phase"] == "won"):
        raise SceneTravelError("cooperative branch acceptance diverged")
    return {"comparison": report, "selection": selected}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-compare")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("compare", "select", "verify", "verify-selection"):
        p = sub.add_parser(command)
        p.add_argument("--left-json", required=True)
        p.add_argument("--right-json", required=True)
        if command == "select":
            p.add_argument("--choice", required=True, choices=("left", "right"))
            p.add_argument("--expected-left-digest", required=True)
            p.add_argument("--expected-right-digest", required=True)
        elif command in ("verify", "verify-selection"):
            p.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = accept_comparison()
        else:
            a, b = _json(args.left_json), _json(args.right_json)
            if args.command == "compare":
                result = compare_party(a, b)
            elif args.command == "select":
                result = select_party(a, b, args.choice,
                                      expected_left_digest=args.expected_left_digest,
                                      expected_right_digest=args.expected_right_digest)
            elif args.command == "verify":
                result = verify_comparison(a, b, _json(args.receipt_json))
            else:
                result = verify_selection(a, b, _json(args.receipt_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
