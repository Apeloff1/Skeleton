"""End-to-end authored human combat campaign production acceptance.

A production receipt binds an atomic source edit to canonical playable
victory, exact decision replay, interactive checkpoints and portable export.
It is not a release, device, rights or author-identity certificate.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import sys
from typing import Any

from skeleton.game.gameplay.combat_campaign_author import (
    demo_author, verify_author_report,
)
from skeleton.game.gameplay.combat_campaign_player import (
    _bounded, export_player_campaign, import_player_campaign,
    new_player_campaign, resume_player_campaign,
)
from skeleton.game.gameplay.combat_campaign_player_acceptance import (
    accept_player_campaign, verify_player_acceptance,
)
from skeleton.game.gameplay.combat_campaign_solver import (
    solve_campaign, verify_campaign_route,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_production_acceptance.v1"


def accept_production(author_report: Any, *,
                      max_states: int = 96, max_depth: int = 12) -> dict[str, Any]:
    """Require an authored, playable and exportable original campaign."""
    authored = verify_author_report(author_report)
    source = authored["after"]
    route = solve_campaign(source=source, max_states=max_states,
                           max_depth=max_depth)
    if route["status"] != "solved":
        raise CombatSessionError(
            "campaign production acceptance requires a proven playable victory"
        )
    if verify_campaign_route(route, expected_source_digest=authored["after_digest"]) != route:
        raise CombatSessionError("campaign production route witness mismatch")
    gameplay = accept_player_campaign(source, route["actions"])
    if verify_player_acceptance(gameplay, source) != gameplay:
        raise CombatSessionError("campaign production playable acceptance mismatch")
    final = resume_player_campaign(
        new_player_campaign(source), route["actions"])
    if (final != route["terminal_session"]
            or final["state_digest"] != gameplay["final_state_digest"]
            or final["state"]["currency"] != gameplay["earned_currency"]):
        raise CombatSessionError("campaign production gameplay state divergence")
    portable = export_player_campaign(final)
    if (portable != route["portable_bundle"]
            or import_player_campaign(portable) != final):
        raise CombatSessionError("campaign production export mismatch")
    result = {
        "schema_version": SCHEMA,
        "author_report": authored,
        "author_receipt": authored["receipt"],
        "source_digest": authored["after_digest"],
        "route_report": route,
        "route_receipt": route["receipt"],
        "playable_acceptance": gameplay,
        "playable_receipt": gameplay["checksum"],
        "portable_bundle": portable,
        "final_state_digest": final["state_digest"],
        "earned_currency": final["state"]["currency"],
        "player_actions": route["actions"],
        "status": "source_to_play_to_save_replay_export_verified",
        "proof_kind": "deterministic_playable_acceptance_not_release_or_signature",
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def verify_production(raw: Any) -> dict[str, Any]:
    """Rebuild every authored edit, decision, gameplay event and export."""
    _bounded(raw)
    obj = _object(raw, {
        "schema_version", "author_report", "author_receipt",
        "source_digest", "route_report", "route_receipt",
        "playable_acceptance", "playable_receipt", "portable_bundle",
        "final_state_digest", "earned_currency", "player_actions",
        "status", "proof_kind", "receipt",
    }, "campaign production receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign production receipt")
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("campaign production receipt checksum mismatch")
    route = _object(obj["route_report"], {
        "schema_version", "source_digest", "start_state_digest",
        "start_session", "limits", "explored_states", "status",
        "incomplete_reasons", "actions", "terminal_session",
        "portable_bundle", "proof_kind", "receipt",
    }, "campaign production route")
    limits = _object(route["limits"], {
        "max_states", "max_depth", "max_choices", "max_frontier",
    }, "campaign production limits")
    if limits["max_choices"] != 16:
        raise CombatSessionError("campaign production choice policy mismatch")
    expected = accept_production(
        obj["author_report"], max_states=limits["max_states"],
        max_depth=limits["max_depth"],
    )
    if expected != obj:
        raise CombatSessionError("campaign production source or replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton combat-campaign-production-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    accept = sub.add_parser("accept")
    accept.add_argument("--author-report-json", required=True)
    accept.add_argument("--max-states", type=int, default=96)
    accept.add_argument("--max-depth", type=int, default=12)
    sub.add_parser("verify").add_argument("--receipt-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = accept_production(demo_author())
        elif args.command == "accept":
            result = accept_production(
                _parse_json(args.author_report_json, "campaign author report"),
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            result = verify_production(
                _parse_json(args.receipt_json, "campaign production receipt"))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
