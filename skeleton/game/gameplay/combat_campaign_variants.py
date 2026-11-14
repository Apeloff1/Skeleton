"""Atomic source-bound combat campaign variant comparison and delivery.

Alternatives are validated authoring transactions, not executable scripts.
Every result is produced by canonical combat, checkpoint and portable bundle
contracts. Victory, HP and currency are never accepted from caller-supplied
snapshots. The unedited baseline is a safe deterministic fallback.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign import (
    finish_campaign, normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.combat_campaign_author import (
    _bounded_json, author_campaign,
)
from skeleton.game.gameplay.combat_campaign_package import package_campaign
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_variants.v1"
POLICY = "victory_then_hero_hp_then_earned_currency_then_source_order_v1"
MAX_ALTERNATIVES = 4


def _summary(
    index: int, operations: list[dict[str, Any]],
    source: dict[str, Any], session: dict[str, Any],
) -> dict[str, Any]:
    state = session["state"]
    return {
        "index": index, "operations": operations,
        "source_digest": dig(source),
        "phase": state["phase"], "hero_hp": state["hero_hp"],
        "earned_currency": state["currency"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
    }


def _rank(summary: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(summary["phase"] == "won"),
        summary["hero_hp"], summary["earned_currency"],
        -summary["index"],
    )


def compare_campaigns(
    raw_source: Any, alternatives: Any, expected_source_digest: Any,
) -> dict[str, Any]:
    """Choose the best verified playable variant without mutating source.

    Selection is deterministic and deliberately simple, not a claim of
    fairness, balance or optimal human play.
    """
    source = normalize_campaign(raw_source)
    source_digest = dig(source)
    if (type(expected_source_digest) is not str
            or expected_source_digest != source_digest):
        raise CombatSessionError("stale campaign comparison source digest")
    if (type(alternatives) is not list
            or not 1 <= len(alternatives) <= MAX_ALTERNATIVES):
        raise CombatSessionError("campaign alternative count outside 1..4")
    baseline = finish_campaign(source)
    summaries = [_summary(0, [], source, baseline)]
    candidates = [(source, baseline)]
    seen = {source_digest}
    for index, edits in enumerate(alternatives, 1):
        receipt = author_campaign(source, edits, source_digest)
        candidate_source = receipt["source"]
        candidate_digest = receipt["after_digest"]
        if candidate_digest in seen:
            raise CombatSessionError("duplicate campaign alternative source")
        seen.add(candidate_digest)
        preview = receipt["preview_session"]
        summaries.append(_summary(
            index, receipt["operations"], candidate_source, preview,
        ))
        candidates.append((candidate_source, preview))
    winner = max(summaries, key=_rank)
    selected_source, selected_session = candidates[winner["index"]]
    bundle = package_campaign(selected_source, selected_session)
    report = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": source_digest,
        "selection_policy": POLICY,
        "alternatives": summaries,
        "selected_index": winner["index"],
        "selected_package": bundle,
        "claim": "deterministic_offline_preview_only",
    }
    report["receipt"] = dig(report)
    _bounded_json(report)
    return report


def verify_comparison(raw: Any) -> dict[str, Any]:
    """Re-run all authored variants, complete playthroughs and selected export."""
    report = _object(raw, {
        "schema_version", "source", "source_digest", "selection_policy",
        "alternatives", "selected_index", "selected_package", "claim",
        "receipt",
    }, "campaign variant report")
    if (report["schema_version"] != SCHEMA
            or report["selection_policy"] != POLICY
            or report["claim"] != "deterministic_offline_preview_only"):
        raise CombatSessionError("unsupported campaign variant report")
    _bounded_json(report)
    alternatives = report["alternatives"]
    if type(alternatives) is not list or not 2 <= len(alternatives) <= 5:
        raise CombatSessionError("invalid campaign variant receipt count")
    if any(type(item) is not dict or "operations" not in item
           for item in alternatives):
        raise CombatSessionError("invalid campaign variant receipt")
    expected = compare_campaigns(
        report["source"],
        [item["operations"] for item in alternatives[1:]],
        report["source_digest"],
    )
    if report != expected:
        raise CombatSessionError("campaign variant report or replay mismatch")
    return expected


def original_variants_demo() -> dict[str, Any]:
    source = original_campaign()
    return compare_campaigns(source, [
        [{"kind": "set-reward", "encounter_id": "reed_watch", "value": 11}],
        [{"kind": "set-reward", "encounter_id": "reed_watch", "value": 12}],
    ], dig(normalize_campaign(source)))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-variants")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Compare original playable authored variants")
    compare = sub.add_parser("compare")
    compare.add_argument("--source-json", required=True)
    compare.add_argument("--alternatives-json", required=True)
    compare.add_argument("--expected-digest", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_variants_demo()
        elif args.command == "compare":
            result = compare_campaigns(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.alternatives_json, "campaign alternatives"),
                args.expected_digest,
            )
        else:
            result = verify_comparison(
                _parse_json(args.report_json, "campaign comparison"),
            )
        print(_bounded_json(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
