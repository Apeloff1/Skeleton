"""End-to-end source-to-playable acceptance for authored chapter campaigns.

The receipt proves that a real authored action script and the bounded route
planner reach the same earned terminal state through a replayable checkpoint.
A failed or exhausted planner never certifies a campaign as playable.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import MAX_BYTES, _size
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_chapter_campaign import (
    MAX_ACTIONS, demo_campaign_actions, export_campaign, import_campaign,
    normalize_campaign, original_campaign, simulate_campaign, verify_campaign,
)
from skeleton.game.gameplay.quest_chapter_campaign_author import (
    apply_edits, verify_edits,
)
from skeleton.game.gameplay.quest_chapter_campaign_route import (
    plan_campaign, verify_campaign_plan,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.quest_chapter_campaign_accept.v1"


def accept_campaign(
    source: Any, actions: Any, *,
    operations: Any = None, split_at: int | None = None,
    max_states: int = 16, max_depth: int = 2,
) -> dict[str, Any]:
    """Verify editing, player actions, checkpoint, route and portable export."""
    baseline = normalize_campaign(source)
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
        raise CombatSessionError("invalid campaign acceptance action batch")
    _size(actions, MAX_BYTES)
    if split_at is None:
        split_at = max(0, len(actions) - 2)
    if type(split_at) is not int or not 0 <= split_at < len(actions):
        raise CombatSessionError("invalid campaign acceptance checkpoint boundary")
    edit = None
    authored = baseline
    if operations is not None:
        edit = apply_edits(
            baseline, operations, expected_digest=dig(baseline),
        )
        verify_edits(edit)
        authored = edit["source"]
    scripted = verify_campaign(simulate_campaign(authored, actions))
    if scripted["state"]["phase"] != "won":
        raise CombatSessionError("campaign script has no earned victory")
    checkpoint = verify_campaign(simulate_campaign(authored, actions[:split_at]))
    if checkpoint["state"]["phase"] != "active":
        raise CombatSessionError("campaign checkpoint is already terminal")
    plan = plan_campaign(
        session=checkpoint, max_states=max_states, max_depth=max_depth,
    )
    if plan["status"] != "found":
        raise CombatSessionError(
            "campaign acceptance requires replay-proven victory; "
            f"planner returned {plan['status']}"
        )
    terminal = verify_campaign_plan(plan, session=checkpoint)
    if terminal != scripted:
        raise CombatSessionError(
            "campaign planner diverges from authored player script"
        )
    bundle = export_campaign(terminal)
    if import_campaign(bundle) != terminal:
        raise CombatSessionError("campaign portable round-trip mismatch")
    result = {
        "schema_version": SCHEMA,
        "source": baseline,
        "source_digest": terminal["source_digest"],
        "operations": operations,
        "edit_receipt": edit,
        "actions": actions,
        "split_at": split_at,
        "max_states": max_states,
        "max_depth": max_depth,
        "checkpoint": checkpoint,
        "plan": plan,
        "terminal": terminal,
        "bundle": bundle,
        "phase": "won",
    }
    result["receipt"] = dig(result)
    _size(result, MAX_BYTES)
    return result


def verify_acceptance(payload: Any) -> dict[str, Any]:
    """Rebuild from canonical source and actions; a checksum is not authority."""
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "operations",
        "edit_receipt", "actions", "split_at", "max_states", "max_depth",
        "checkpoint", "plan", "terminal", "bundle", "phase", "receipt",
    }, "campaign acceptance report")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign acceptance report")
    rebuilt = accept_campaign(
        obj["source"], obj["actions"], operations=obj["operations"],
        split_at=obj["split_at"], max_states=obj["max_states"],
        max_depth=obj["max_depth"],
    )
    if rebuilt != obj:
        raise CombatSessionError("campaign acceptance replay mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-campaign-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    check = sub.add_parser("check")
    check.add_argument("--source-json", required=True)
    check.add_argument("--actions-json", required=True)
    check.add_argument("--operations-json")
    check.add_argument("--split-at", type=int)
    check.add_argument("--max-states", type=int, default=16)
    check.add_argument("--max-depth", type=int, default=2)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = accept_campaign(original_campaign(), demo_campaign_actions())
        elif args.command == "check":
            result = accept_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.actions_json, "campaign actions"),
                operations=(
                    _parse_json(args.operations_json, "campaign edits")
                    if args.operations_json is not None else None
                ),
                split_at=args.split_at,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            result = verify_acceptance(
                _parse_json(args.report_json, "campaign acceptance report")
            )
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
