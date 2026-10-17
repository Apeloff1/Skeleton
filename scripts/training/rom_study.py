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
    progress = commands.add_parser(
        "triangle-lens-progress",
        help="inspect source-pinned completed/pending steps of a 200-lens model session",
    )
    progress.add_argument("--receipt", type=Path, required=True)
    progress.add_argument("--review-receipt", type=Path, required=True)
    progress.add_argument("--source-sha256", required=True)
    progress.add_argument("--output-dir", type=Path, required=True)
    progress.add_argument("--semantic-checkpoint", type=Path, required=True)
    progress.add_argument("--run-index", type=int, default=0)
    progress.add_argument("--seed", type=int, default=0)
    progress.add_argument("--max-new-tokens", type=int, default=192)
    coverage = commands.add_parser(
        "triangle-lens-audit",
        help="audit source support for all 200 authored Jeeves lenses (43 legacy optional)",
    )
    coverage.add_argument("--receipt", required=True, type=Path)
    coverage.add_argument("--source-sha256", required=True)
    coverage.add_argument("--start-episode", type=int, default=0)
    coverage.add_argument("--limit", type=int, default=8)
    coverage.add_argument("--lens-count", type=int, choices=(43, 200), default=200)
    coverage.add_argument("--semantic-lens-set", type=Path)
    lenses = commands.add_parser(
        "triangle-lenses",
        help="inspect all 200 authored Jeeves lenses or legacy 43 selection",
    )
    lenses.add_argument("--receipt", required=True, type=Path)
    lenses.add_argument("--source-sha256", required=True)
    lenses.add_argument("--run-index", type=int, default=0)
    lenses.add_argument("--lens-count", type=int, choices=(43, 200), default=200)
    lenses.add_argument(
        "--output-dir", type=Path,
        help="optionally pin the exact 200-lens catalog or a legacy 43-lens selection",
    )
    status = commands.add_parser(
        "triangle-status", help="verify a native ROM training triangle without loading model weights"
    )
    status.add_argument("--receipt", required=True, type=Path)
    status.add_argument("--source-sha256", required=True)
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
    triangle = commands.add_parser(
        "train-triangle",
        help="one-command approved native gameplay, Dragon inspection, and local adversarial review",
    )
    triangle.add_argument("--root", required=True, type=Path)
    triangle.add_argument("--approvals", required=True, type=Path)
    triangle.add_argument("--output-dir", required=True, type=Path)
    triangle.add_argument("--reviewer-checkpoint", required=True, type=Path)
    triangle.add_argument("--snapshot", required=True, type=Path,
                          help="hash-pinned frozen inventory for efficient restartable campaigns")
    triangle.add_argument("--cursor")
    triangle.add_argument("--limit", type=int, default=32)
    triangle.add_argument("--max-pages", type=int, default=1,
                          help="0 runs all frozen pages in the foreground")
    triangle.add_argument("--runs", type=int, default=12)
    triangle.add_argument("--steps", type=int, default=24)
    triangle.add_argument("--seed", type=int, default=0)
    triangle.add_argument("--neural-world", action="store_true")
    triangle.add_argument("--neural-epochs", type=int, default=4)
    triangle.add_argument("--neural-width", type=int, default=8)
    triangle.add_argument("--review-seed", type=int, default=0)
    triangle.add_argument("--review-tokens", type=int, default=160)
    triangle.add_argument(
        "--semantic-checkpoint", type=Path,
        help="opt in to real local model inference for all 200 authored Jeeves lenses",
    )
    triangle.add_argument(
        "--semantic-lens-set", type=Path,
        help="optional pinned complete 200-lens or legacy 43-lens key manifest",
    )
    triangle.add_argument(
        "--semantic-all-runs", action="store_true", default=True,
        help="execute all configured lenses for EVERY native episode (default)",
    )
    triangle.add_argument(
        "--semantic-first-run-only", action="store_false",
        dest="semantic_all_runs",
        help="explicit legacy resource-saving option: only episode zero",
    )
    triangle.add_argument("--semantic-seed", type=int, default=0)
    triangle.add_argument("--semantic-tokens", type=int, default=192)
    triangle.add_argument("--semantic-lens-count", type=int, choices=(43, 200), default=200)
    corpus = commands.add_parser(
        "export-triangle-corpus",
        help="replay the independent critic and export weighted Jeeves candidate training views",
    )
    corpus.add_argument("--receipt", required=True, type=Path)
    corpus.add_argument("--review-receipt", required=True, type=Path)
    corpus.add_argument("--source-sha256", required=True)
    corpus.add_argument("--reviewer-checkpoint", required=True, type=Path)
    corpus.add_argument("--output-dir", required=True, type=Path)
    corpus.add_argument(
        "--semantic-lens-set", type=Path,
        help="strict catalog manifest: exactly 200 original or 43 legacy keys",
    )
    corpus.add_argument(
        "--semantic-review-receipt", type=Path, action="append",
        help="repeat once per native episode to export a complete, replay-verified v4 lens corpus",
    )
    corpus.add_argument("--semantic-lens-count", type=int, choices=(43, 200), default=200)
    corpus.add_argument(
        "--semantic-checkpoint", type=Path,
        help="required with --semantic-review-receipt to replay original model inferences",
    )
    native_semantics = commands.add_parser(
        "execute-43-lenses",
        help="run and replay all 43 canonical Jeeves semantic lens hypotheses on native emulator evidence",
    )
    native_semantics.add_argument("--receipt", required=True, type=Path)
    native_semantics.add_argument("--review-receipt", required=True, type=Path)
    native_semantics.add_argument("--source-sha256", required=True)
    native_semantics.add_argument("--critic-checkpoint", required=True, type=Path)
    native_semantics.add_argument("--semantic-checkpoint", required=True, type=Path)
    native_semantics.add_argument("--output-dir", required=True, type=Path)
    native_semantics.add_argument("--semantic-lens-set", type=Path)
    native_semantics.add_argument("--run-index", type=int, default=0)
    native_semantics.add_argument("--seed", type=int, default=0)
    native_semantics.add_argument("--max-new-tokens", type=int, default=192)
    native_200 = commands.add_parser(
        "execute-200-lenses",
        help="run 200 real source-bound governed Jeeves semantic lens model generations",
    )
    native_200.add_argument("--receipt", required=True, type=Path)
    native_200.add_argument("--review-receipt", required=True, type=Path)
    native_200.add_argument("--source-sha256", required=True)
    native_200.add_argument("--critic-checkpoint", required=True, type=Path)
    native_200.add_argument("--semantic-checkpoint", required=True, type=Path)
    native_200.add_argument("--output-dir", required=True, type=Path)
    native_200.add_argument("--semantic-lens-set", type=Path)
    native_200.add_argument("--run-index", type=int, default=0)
    native_200.add_argument("--seed", type=int, default=0)
    native_200.add_argument("--max-new-tokens", type=int, default=192)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "triangle-lens-progress":
            from skeleton.ai.training.rom_triangle_lens_progress import (
                native_lens_progress,
            )
            from skeleton.ai.model_runtime.offline_chat import load_offline_engine
            runtime = load_offline_engine(args.semantic_checkpoint).runtime
            result = native_lens_progress(
                args.receipt, args.review_receipt,
                source_sha256=args.source_sha256,
                output_dir=args.output_dir, semantic_runtime=runtime,
                run_index=args.run_index,
                seed=args.seed, max_new_tokens=args.max_new_tokens,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.operation == "triangle-lens-audit":
            from skeleton.ai.training.rom_triangle_campaign import (
                read_receipt_document, load_operator_semantic_lens_set,
            )
            from skeleton.ai.training.rom_study import verified_rom_receipt
            from skeleton.jeeves.game_emulator_triangle_lens_coverage import (
                audit_43_lens_coverage, verify_43_lens_coverage,
            )
            verified = verified_rom_receipt(
                args.receipt, expected_source_sha256=args.source_sha256,
            )
            document, digest = read_receipt_document(args.receipt)
            if digest != verified["receipt_sha256"]:
                raise RomStudyError("43-lens coverage source changed since audit")
            pinned = (
                load_operator_semantic_lens_set(args.semantic_lens_set)
                if args.semantic_lens_set is not None else ()
            )
            report = audit_43_lens_coverage(
                document["candidate_evidence"], document["training_triangle"],
                start_episode=args.start_episode, limit=args.limit,
                requested_keys=pinned,
                lens_budget=args.lens_count,
            )
            verify_43_lens_coverage(
                document["candidate_evidence"], document["training_triangle"], report,
            )
            print(json.dumps(report, sort_keys=True))
            return 0
        if args.operation in ("execute-43-lenses", "execute-200-lenses"):
            from skeleton.ai.training.rom_triangle_campaign import (
                execute_native_43_lens_review, load_operator_semantic_lens_set,
            )
            from skeleton.ai.model_runtime.offline_chat import load_offline_engine
            requested = (
                load_operator_semantic_lens_set(args.semantic_lens_set)
                if args.semantic_lens_set is not None else ()
            )
            critic = load_offline_engine(args.critic_checkpoint).runtime
            semantic = load_offline_engine(args.semantic_checkpoint).runtime
            result = execute_native_43_lens_review(
                args.receipt, args.review_receipt,
                source_sha256=args.source_sha256,
                output_dir=args.output_dir, critic_runtime=critic,
                semantic_runtime=semantic, run_index=args.run_index,
                requested_keys=requested, seed=args.seed,
                max_new_tokens=args.max_new_tokens,
                lens_budget=(200 if args.operation == "execute-200-lenses" else 43),
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.operation == "triangle-lenses":
            from skeleton.ai.training.rom_triangle_campaign import (
                inspect_native_episode_lenses,
            )
            result = inspect_native_episode_lenses(
                args.receipt, source_sha256=args.source_sha256,
                run_index=args.run_index, output_dir=args.output_dir,
                lens_budget=args.lens_count,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.operation == "export-triangle-corpus":
            from skeleton.ai.model_runtime.offline_chat import load_offline_engine
            from skeleton.ai.training.rom_triangle_campaign import (
                export_reviewed_candidate_corpus, load_operator_semantic_lens_set,
            )
            keys = (
                load_operator_semantic_lens_set(args.semantic_lens_set)
                if args.semantic_lens_set is not None else ()
            )
            runtime = load_offline_engine(args.reviewer_checkpoint).runtime
            if bool(args.semantic_review_receipt) != (args.semantic_checkpoint is not None):
                raise RomStudyError("semantic review receipts and checkpoint must be supplied together")
            semantic_runtime = (
                load_offline_engine(args.semantic_checkpoint).runtime
                if args.semantic_checkpoint is not None else None
            )
            result = export_reviewed_candidate_corpus(
                args.receipt, args.review_receipt,
                source_sha256=args.source_sha256,
                output_dir=args.output_dir, runtime=runtime,
                requested_semantic_lens_keys=keys,
                semantic_review_receipts=tuple(args.semantic_review_receipt or ()),
                semantic_runtime=semantic_runtime,
                semantic_lens_budget=args.semantic_lens_count,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.operation == "triangle-status":
            from skeleton.ai.training.rom_triangle_campaign import (
                read_receipt_document,
            )
            from skeleton.ai.training.rom_study import verified_rom_receipt
            from skeleton.jeeves.game_emulator_triangle import verify_training_triangle
            verified = verified_rom_receipt(
                args.receipt, expected_source_sha256=args.source_sha256,
            )
            document, digest = read_receipt_document(args.receipt)
            if digest != verified["receipt_sha256"]:
                raise RomStudyError("ROM training receipt changed since verification")
            evidence, triangle = document["candidate_evidence"], document["training_triangle"]
            verify_training_triangle(evidence, triangle)
            from skeleton.jeeves.game_emulator_triangle_semantics import (
                EXTENDED_SEMANTIC_LENS_BUDGET, route_episode_semantic_lenses,
            )
            previews = [
                route_episode_semantic_lenses(
                    episode, max_lenses=EXTENDED_SEMANTIC_LENS_BUDGET,
                )
                for episode in triangle["episode_lens_references"][:3]
            ]
            print(json.dumps({
                "semantic_router": "all_200_canonical_jeeves_lens_system",
                "semantic_lens_selection_budget": EXTENDED_SEMANTIC_LENS_BUDGET,
                "semantic_episode_previews": [{
                    "source_trace_sha256": item["source_native_trace_sha256"],
                    "routed": item["actually_routed_lenses"],
                    "lens_keys": [lens["lens_key"] for lens in item["routes"]],
                    "catalog_digest": item["canonical_catalog_sha256"],
                    "factual_assertions_authorized": False,
                } for item in previews],
                "state": "triangle_native_evidence_verified",
                "receipt_sha256": verified["receipt_sha256"],
                "source_sha256": args.source_sha256,
                "triangle_digest": triangle["triangle_digest"],
                "vertices": triangle["vertices"],
                "source_diversity": triangle["source_diversity"],
                "adversarial_challenges": len(triangle["adversarial_challenge_queue"]),
                "real_semantic_media_witness_verified": False,
                "production_jeeves_weight_updates": 0,
            }, sort_keys=True))
            return 0
        if args.operation == "review-triangle":
            from skeleton.ai.model_runtime.offline_chat import load_offline_engine
            from skeleton.ai.training.rom_triangle_campaign import review_one_receipt
            runtime = load_offline_engine(args.reviewer_checkpoint).runtime
            result = review_one_receipt(
                args.receipt, expected_source_sha256=args.source_sha256,
                output_dir=args.output_dir, runtime=runtime,
                seed=args.seed, max_new_tokens=args.max_new_tokens,
            )
            print(json.dumps(result, sort_keys=True))
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
        if args.operation == "train-triangle":
            from skeleton.ai.model_runtime.offline_chat import load_offline_engine
            from skeleton.ai.training.rom_triangle_campaign import (
                triangle_campaign_page, load_operator_semantic_lens_set,
            )
            if (args.semantic_lens_set is not None or args.semantic_all_runs
                    or args.semantic_lens_count == 200) and args.semantic_checkpoint is None:
                raise RomStudyError("200-lens mode requires a real installed semantic checkpoint")
            keys = (
                load_operator_semantic_lens_set(args.semantic_lens_set)
                if args.semantic_lens_set is not None else ()
            )
            runtime = load_offline_engine(args.reviewer_checkpoint).runtime
            semantic_runtime = (
                load_offline_engine(args.semantic_checkpoint).runtime
                if args.semantic_checkpoint is not None else None
            )
            while True:
                result = triangle_campaign_page(
                    args.root, args.approvals, args.output_dir, runtime,
                    cursor=cursor, limit=args.limit, runs=args.runs,
                    steps=args.steps, seed=args.seed,
                    neural_world=args.neural_world,
                    neural_epochs=args.neural_epochs,
                    neural_width=args.neural_width,
                    inventory_snapshot=frozen,
                    review_seed=args.review_seed,
                    review_tokens=args.review_tokens,
                    semantic_runtime=semantic_runtime,
                    semantic_lens_keys=keys,
                    semantic_all_runs=args.semantic_all_runs or args.semantic_lens_count == 200,
                    semantic_seed=args.semantic_seed,
                    semantic_tokens=args.semantic_tokens,
                    semantic_lens_budget=args.semantic_lens_count,
                )
                pages += 1
                print(json.dumps({
                    **result, "page_number": pages,
                    "semantic_lens_budget_requested": args.semantic_lens_count,
                    "all_native_episodes_required": args.semantic_lens_count == 200,
                    "model_digest": runtime.model_digest,
                    "next_cursor_is_safe_to_advance": (
                        result["review_failures_needing_retry"] == 0
                    ),
                }, sort_keys=True), flush=True)
                if result["review_failures_needing_retry"]:
                    # Do not advance a batch past failed/unstored independent
                    # reviews. Reissue with the SAME cursor; create-only
                    # gameplay receipts prevent duplicate policy training.
                    return 3
                cursor = result["next_cursor"]
                if cursor is None or (args.max_pages and pages >= args.max_pages):
                    return 0
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
