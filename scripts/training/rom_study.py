"""Inspect all local ROM candidates and train eligible ROM Q-policies on the real emulator lab.

No ROM download, emulated-completion claim, or automatic production-weight change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.training.rom_study import (
    RomStudyError, inventory_page, train_page,
)
from skeleton.ai.training.rom_inventory_snapshot import (
    freeze_rom_inventory, load_frozen_inventory, frozen_inventory_page,
)
from skeleton.ai.training.rom_fleet_audit import audit_fleet_page, audit_fleet_all


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="operation", required=True)
    inventory = commands.add_parser("inventory", help="read-only ROM inventory")
    inventory.add_argument("--root", required=True, type=Path)
    inventory.add_argument("--cursor")
    inventory.add_argument("--limit", type=int, default=64)
    freeze = commands.add_parser("freeze-inventory", help="pin a large ROM inventory once")
    freeze.add_argument("--root", required=True, type=Path)
    freeze.add_argument("--output-dir", required=True, type=Path)
    freeze.add_argument("--name", default="rom-library-snapshot.json")
    inventory.add_argument("--snapshot", type=Path,
                           help="use a previously frozen exact file census")
    bundle = commands.add_parser(
        "inspect-bundle", help="hash a lawful multi-file disc folder for independent review"
    )
    bundle.add_argument("--root", required=True, type=Path)
    bundle.add_argument("--entrypoint", required=True)
    reviewer = commands.add_parser(
        "review-triangle", help="run a separate local native LLM red-team against ROM evidence"
    )
    reviewer.add_argument("--receipt", required=True, type=Path)
    reviewer.add_argument("--source-sha256", required=True)
    reviewer.add_argument("--reviewer-checkpoint", required=True, type=Path)
    reviewer.add_argument("--output-dir", required=True, type=Path)
    reviewer.add_argument("--seed", type=int, default=0)
    reviewer.add_argument("--max-new-tokens", type=int, default=160)
    audit = commands.add_parser("audit-fleet", help="read-only verified fleet coverage report")
    audit.add_argument("--root", required=True, type=Path)
    audit.add_argument("--snapshot", required=True, type=Path)
    audit.add_argument("--approvals", required=True, type=Path)
    audit.add_argument("--output-dir", required=True, type=Path)
    audit.add_argument("--cursor")
    audit.add_argument("--limit", type=int, default=64)
    audit.add_argument("--max-pages", type=int, default=1,
                       help="0 scans all snapshot pages without reloading the manifest")
    train = commands.add_parser("train-all", help="run approved Q-policy learning per ROM")
    train.add_argument("--root", required=True, type=Path)
    train.add_argument("--approvals", required=True, type=Path)
    train.add_argument("--output-dir", required=True, type=Path)
    train.add_argument("--cursor")
    train.add_argument("--snapshot", type=Path, help="reuse frozen ROM inventory for large libraries")
    train.add_argument("--limit", type=int, default=32)
    train.add_argument("--max-pages", type=int, default=1,
                       help="0 scans all pages in this foreground invocation")
    train.add_argument("--runs", type=int, default=12)
    train.add_argument("--steps", type=int, default=24)
    train.add_argument("--seed", type=int, default=0)
    train.add_argument("--neural-world", action="store_true",
                       help="also train a checkpointed candidate neural world model from replay evidence")
    train.add_argument("--neural-epochs", type=int, default=4)
    train.add_argument("--neural-width", type=int, default=8)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "review-triangle":
            import hashlib
            from skeleton.ai.training.rom_study import (
                _hash, _private_output, _safe_path, _save_new, verified_rom_receipt,
            )
            from skeleton.jeeves.game_emulator_triangle import verify_training_triangle
            from skeleton.jeeves.game_emulator_triangle_native_reviewer import (
                run_native_adversarial_review, verify_native_adversarial_review,
            )
            from skeleton.ai.model_runtime.offline_chat import load_offline_engine
            verified = verified_rom_receipt(
                args.receipt, expected_source_sha256=args.source_sha256,
            )
            source_path = _safe_path(args.receipt)
            source_raw = source_path.read_bytes()
            if _hash(source_raw) != verified["receipt_sha256"]:
                raise RomStudyError("ROM training receipt changed after independent verification")
            source = json.loads(source_raw)
            evidence, triangle = source["candidate_evidence"], source["training_triangle"]
            verify_training_triangle(evidence, triangle)
            output_dir = _private_output(args.output_dir)
            # Checkpoint admission uses existing canonical native runtime,
            # without reaching a hosted provider or editing production weights.
            reviewer_engine = load_offline_engine(args.reviewer_checkpoint)
            runtime = reviewer_engine.runtime
            fingerprint = hashlib.sha256(json.dumps({
                "receipt": verified["receipt_sha256"], "model": runtime.model_digest,
                "seed": args.seed, "tokens": args.max_new_tokens,
            }, sort_keys=True).encode()).hexdigest()
            destination = output_dir / (
                "triangle-review-" + args.source_sha256[:16] + "-" + fingerprint[:24] + ".json"
            )
            if destination.exists() or destination.is_symlink():
                record = json.loads(_safe_path(destination).read_bytes())
                verify_native_adversarial_review(evidence, triangle, record)
                if record["independent_local_transformer_sha256"] != runtime.model_digest:
                    raise RomStudyError("prior adversarial review model differs")
                print(json.dumps({"state": "previous_verified_native_model_review",
                                  "filename": destination.name,
                                  "review_digest": record["review_digest"]}, sort_keys=True))
                return 0
            record = run_native_adversarial_review(
                evidence, triangle, runtime, seed=args.seed,
                max_new_tokens=args.max_new_tokens,
            )
            verify_native_adversarial_review(evidence, triangle, record)
            _save_new(destination, record)
            print(json.dumps({
                "state": "native_model_review_executed_requires_manual_adjudication",
                "filename": destination.name,
                "review_digest": record["review_digest"],
                "passes_executed": record["passes_executed"],
                "structured_source_bound_passes": record["structured_source_bound_passes"],
                "production_jeeves_weight_updates": 0,
            }, sort_keys=True))
            return 0
        if args.operation == "inspect-bundle":
            from skeleton.jeeves.game_emulator_operator_content import (
                operator_directory_content,
            )
            bundle, _ = operator_directory_content(args.root, args.entrypoint)
            data = bundle.as_dict()
            print(json.dumps({
                "schema_version": data["schema_version"],
                "entrypoint": bundle.entrypoint,
                "bundle_sha256": bundle.bundle_digest,
                "source_sha256": bundle.source_digest,
                "files": [{
                    "name": item["name"], "size_bytes": item["size_bytes"],
                    "sha256": item["sha256"],
                } for item in data["files"]],
                "source_rights_reviewed": False,
                "training_permitted": False,
                "emulator_execution_checked": False,
            }, sort_keys=True))
            return 0
        if args.operation == "audit-fleet":
            report = (
                audit_fleet_page(
                    args.root, args.snapshot, args.approvals, args.output_dir,
                    cursor=args.cursor, limit=args.limit,
                ) if args.max_pages == 1 else
                audit_fleet_all(
                    args.root, args.snapshot, args.approvals, args.output_dir,
                    cursor=args.cursor, limit=args.limit,
                    max_pages=args.max_pages,
                )
            )
            print(json.dumps(report, sort_keys=True))
            return 0
        if args.operation == "freeze-inventory":
            result = freeze_rom_inventory(
                args.root, args.output_dir, name=args.name,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        frozen = (
            load_frozen_inventory(args.snapshot, root=args.root)
            if getattr(args, "snapshot", None) is not None else None
        )
        if args.operation == "inventory":
            listing = (
                frozen_inventory_page(frozen, root=args.root,
                                      cursor=args.cursor, limit=args.limit)
                if frozen is not None
                else inventory_page(args.root, cursor=args.cursor, limit=args.limit)
            )
            print(json.dumps(listing, sort_keys=True))
            return 0
        if type(args.max_pages) is not int or not 0 <= args.max_pages <= 100_000:
            raise RomStudyError("max_pages must be 0 (whole inventory) or 1..100000")
        cursor, pages = args.cursor, 0
        while True:
            result = train_page(
                args.root, args.approvals, args.output_dir, cursor=cursor,
                limit=args.limit, runs=args.runs, steps=args.steps, seed=args.seed,
                neural_world=args.neural_world, neural_epochs=args.neural_epochs,
                neural_width=args.neural_width, inventory_snapshot=frozen,
            )
            pages += 1
            print(json.dumps({
                "page_number": pages,
                "initial_cursor": cursor,
                "next_cursor": result["next_cursor"],
                "inventory_exhausted": result["finished_inventory"],
                "q_policies_updated": result["q_policy_training_completed"],
                "executed_without_updates": result["q_policy_runs_without_updates"],
                "blocked_or_unreviewed": result["blocked_or_unreviewed"],
                "neural_candidates_trained": result["neural_candidate_training_completed"],
                "results": result["page_results"],
                "neural_weights_updated": 0,
                "production_weights_modified": False,
            }, sort_keys=True), flush=True)
            cursor = result["next_cursor"]
            if cursor is None or args.max_pages and pages >= args.max_pages:
                return 0
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print("ROM training blocked: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
