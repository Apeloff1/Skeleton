"""Local operator commands for independent production game-design review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .jeeves_game_design_review_gate import (
    ASSESSMENT_SCHEMA, CRITERIA, SCHEMA,
    adjudicate, prepare, publish_adjudication,
)
from .jeeves_production_game_train import ProductionCheckpointError, _strict_json
from .jeeves_production_readiness import _save_new_private


def blank_assessment(packet_path: Path, reviewer_id: str, output: Path) -> dict[str, Any]:
    """Make a clearly INCOMPLETE human scoring worksheet; not synthetic ratings."""
    if not 3 <= len(reviewer_id) <= 80 or not reviewer_id.strip():
        raise ProductionCheckpointError("reviewer ID must have at least 3 characters")
    if packet_path.is_symlink() or not packet_path.is_file():
        raise ProductionCheckpointError("review packet missing")
    import hashlib
    raw = packet_path.read_bytes()
    packet = _strict_json(raw)
    if packet.get("schema_version") != SCHEMA or len(packet.get("entries", [])) != 24:
        raise ProductionCheckpointError("review worksheet requires a full blind packet")
    form = {
        "schema_version": ASSESSMENT_SCHEMA,
        "packet_sha256": hashlib.sha256(raw).hexdigest(),
        "reviewer_id": reviewer_id,
        "ratings": [
            {
                "item_id": row["item_id"],
                "scores_a": dict.fromkeys(CRITERIA, None),
                "scores_b": dict.fromkeys(CRITERIA, None),
                "critical_a": None,
                "critical_b": None,
                "evidence_note": "",
            }
            for row in packet["entries"]
        ],
        "human_review_complete": False,
        "model_promotion": False,
    }
    _save_new_private(output, (
        json.dumps(form, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8"))
    return {
        "status": "human_review_template_only",
        "reviewer_id": reviewer_id,
        "worksheet_path": str(output.resolve()),
        "scores_entered": 0,
        "candidate_promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = sub.add_parser("prepare", help="Produce a blinded A/B review packet")
    prepare_cmd.add_argument("--benchmark", type=Path, required=True)
    prepare_cmd.add_argument("--packet", type=Path, required=True)
    prepare_cmd.add_argument("--private-key", type=Path, required=True)
    worksheet_cmd = sub.add_parser("worksheet", help="Produce one blank human score sheet")
    worksheet_cmd.add_argument("--packet", type=Path, required=True)
    worksheet_cmd.add_argument("--reviewer-id", required=True)
    worksheet_cmd.add_argument("--output", type=Path, required=True)
    judge = sub.add_parser("adjudicate", help="Validate two completed independent reviews")
    judge.add_argument("--packet", type=Path, required=True)
    judge.add_argument("--private-key", type=Path, required=True)
    judge.add_argument("--reviewer-a", type=Path, required=True)
    judge.add_argument("--reviewer-b", type=Path, required=True)
    judge.add_argument("--output", type=Path, required=True)
    judge.add_argument("--min-mean-gain", type=float, default=0.40)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(
                source_report=args.benchmark, public_packet=args.packet,
                private_key=args.private_key,
            )
        elif args.command == "worksheet":
            result = blank_assessment(args.packet, args.reviewer_id, args.output)
        else:
            result = publish_adjudication(adjudicate(
                packet_path=args.packet, private_key_path=args.private_key,
                assessment_paths=(args.reviewer_a, args.reviewer_b),
                min_mean_improvement=args.min_mean_gain,
            ), args.output)
        print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False))
        return 0 if result.get("status") != "quality_gate_failed" else 3
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
