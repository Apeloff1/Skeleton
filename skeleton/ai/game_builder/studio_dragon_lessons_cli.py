"""Operator-visible Dragon corrective lessons for original game production.

Only actual verified campaign evidence is eligible. Approving a proposal
creates a reviewed operational draft; it does not update model weights,
silently amend the almanac or authorize recurring observation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_campaign_cli import parse_campaign_order_file
from .studio_dragon_learning_bridge import (
    propose_dragon_operational_lessons,
    review_dragon_operational_lesson,
    inspect_dragon_reviewed_lessons,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--propose", action="store_true")
    actions.add_argument("--inspect-reviewed", action="store_true")
    actions.add_argument("--review-candidate")
    parser.add_argument("--decision", choices=(
        "approve_for_reviewed_knowledge", "reject", "needs_more_evidence",
    ))
    parser.add_argument("--reviewer-note")
    parser.add_argument("--human-reviewed", action="store_true")
    parser.add_argument("--authorize-local-operation", action="store_true")
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args(argv)
    if not args.authorize_local_operation:
        parser.error("Dragon operational evidence requires explicit local authority")
    try:
        order = parse_campaign_order_file(args.order)
        if args.propose:
            result = propose_dragon_operational_lessons(
                order, args.campaign, authorized=True, limit=args.limit,
            )
        elif args.inspect_reviewed:
            result = inspect_dragon_reviewed_lessons(
                order, args.campaign, authorized=True,
            )
        else:
            if not args.human_reviewed or not args.decision or not args.reviewer_note:
                parser.error("review requires explicit human-reviewed decision and note")
            result = review_dragon_operational_lesson(
                order, args.campaign, args.review_candidate,
                args.decision, args.reviewer_note,
                authorized=True, human_reviewed=True,
            )
    except (OSError, ValueError, RuntimeError, PermissionError) as exc:
        print(json.dumps({"success": False, "error": type(exc).__name__},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
