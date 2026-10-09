"""Self-contained offline inference CLI for frozen Windows/Linux executables.

This is an application entrypoint, not a new inference owner. It uses only
operator-supplied local model artifacts through the existing canonical
native and llama.cpp engine adapters. No model is fetched or generated.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

from .offline_workspace import DurableOfflineSession
from .offline_library import OfflineDocumentLibrary, OfflineLibraryError, render_local_context
from .offline_readiness import inspect_local_readiness
from .offline_index_queue import OfflineIndexQueue
from .offline_snapshot import (
    create_snapshot, verify_snapshot, restore_snapshot,
)
from .offline_audit import audit_database
from .local_ai import (
    OfflineAISession,
    OfflineGGUFSession,
    load_native_checkpoint,
    smoke_offline_native_inference,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="SkeletonOffline",
        description="Run Skeleton AI using a trusted local checkpoint or GGUF deployment.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--model", help="local Skeleton native checkpoint JSON")
    source.add_argument("--deployment", help="SHA-256 pinned llama.cpp / GGUF manifest JSON")
    parser.add_argument("--prompt", help="text to generate from the local model")
    parser.add_argument("--max-output-tokens", type=int, default=16)
    parser.add_argument("--backup-in", help="restore model-matched transcript before inference")
    parser.add_argument("--backup-out", help="atomically save completed transcript after inference")
    parser.add_argument("--workspace", help="local SQLite file for automatically durable conversations")
    parser.add_argument("--session-id", default="default", help="revisioned conversation id inside the workspace")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--doctor", action="store_true", help="verify local artifacts without generating text")
    parser.add_argument("--qualify-model", action="store_true", help="perform two local inference turns with persisted context recovery")
    capabilities = parser.add_mutually_exclusive_group()
    capabilities.add_argument("--capability-file", help="selected JSON task for offline deterministic execution")
    capabilities.add_argument("--capability-graph-file", help="execute a bounded local graph of deterministic capability operations")
    capabilities.add_argument("--capability-list", action="store_true", help="list available model-free deterministic operations")
    capabilities.add_argument("--game-preview", action="store_true", help="open native Tk offline playable game preview")
    capabilities.add_argument("--game-preview-check", action="store_true", help="verify 32 frames of native game logic without opening desktop")
    capabilities.add_argument("--chip8-demo-output", help="new original legal CHIP-8 homebrew ROM output file")
    capabilities.add_argument("--chip8-demo-check", action="store_true", help="execute native CHIP-8 homebrew through a winning controller replay")
    capabilities.add_argument("--chip8-export-capsule", help="rights-attested original 5-8 tile capsule for CHIP-8")
    parser.add_argument("--chip8-rom-output", help="unused output .ch8 filename for --chip8-export-capsule")
    parser.add_argument("--game-seed", type=int, help="deterministic seed for explicit native game preview")
    parser.add_argument("--game-project", help="user-selected, verified portable game project for native preview")
    parser.add_argument("--library", help="user-owned local SQLite document search index")
    parser.add_argument("--index-dir", help="index an explicitly selected local text directory")
    parser.add_argument("--search", help="search indexed local documents without any model")
    parser.add_argument("--use-library", action="store_true", help="include bounded retrieved excerpts in local model request")
    parser.add_argument("--context-limit", type=int, default=3, help="maximum local excerpts for contextual inference")
    parser.add_argument("--queue-db", help="durable local SQLite indexing job queue")
    parser.add_argument("--enqueue-dir", help="enqueue explicit local document directory")
    parser.add_argument("--queue-library", help="target local FTS5 SQLite index for queued work")
    parser.add_argument("--run-queue", action="store_true", help="process queued local indexing jobs synchronously")
    parser.add_argument("--queue-status", action="store_true", help="show durable local index jobs")
    parser.add_argument("--cancel-queue-job", help="cancel a queued indexing job by id")
    parser.add_argument("--retry-queue-job", help="retry a terminal failed indexing job by id")
    parser.add_argument("--drain-limit", type=int, default=5, help="maximum queued indexing jobs per invocation")
    parser.add_argument("--snapshot-to", help="publish portable SQLite recovery folder")
    parser.add_argument("--restore-from", help="restore verified SQLite recovery folder")
    parser.add_argument("--verify-snapshot", help="verify portable local recovery folder")
    parser.add_argument("--snapshot-workspace", help="selected chat SQLite file")
    parser.add_argument("--snapshot-library", help="selected document SQLite file")
    parser.add_argument("--snapshot-queue", help="selected indexing queue SQLite file")
    parser.add_argument("--audit-workspace", help="inspect local conversation SQLite semantics")
    parser.add_argument("--audit-library", help="inspect local FTS5 SQLite semantics")
    parser.add_argument("--audit-queue", help="inspect local job queue SQLite semantics")
    parser.add_argument(
        "--native-smoke", action="store_true",
        help="run a small locally constructed test model (NOT a trained assistant)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    library_mode = args.index_dir is not None or args.search is not None
    snapshot_mode = bool(
        args.snapshot_to or args.restore_from or args.verify_snapshot
    )
    audits = {
        "workspace": args.audit_workspace,
        "library": args.audit_library,
        "queue": args.audit_queue,
    }
    audit_mode = any(path is not None for path in audits.values())
    queue_mode = bool(
        args.enqueue_dir or args.run_queue or args.queue_status
        or args.cancel_queue_job or args.retry_queue_job
    )
    chip8_mode = (
        args.chip8_demo_output is not None
        or args.chip8_export_capsule is not None
        or args.chip8_demo_check
    )
    if args.chip8_rom_output and args.chip8_export_capsule is None:
        print("--chip8-rom-output requires --chip8-export-capsule", file=sys.stderr)
        return 2
    if args.chip8_export_capsule and not args.chip8_rom_output:
        print("--chip8-export-capsule requires --chip8-rom-output", file=sys.stderr)
        return 2
    if chip8_mode:
        if (
            args.model or args.deployment or args.prompt or args.backup_in
            or args.backup_out or args.workspace or args.native_smoke
            or args.doctor or args.qualify_model or args.library
            or args.use_library or library_mode or queue_mode or snapshot_mode
            or audit_mode or args.queue_db or args.queue_library
            or args.snapshot_workspace or args.snapshot_library
            or args.snapshot_queue or args.game_seed is not None
            or args.game_project is not None
        ):
            print("original CHIP-8 ROM export cannot combine with model, state or game preview",
                  file=sys.stderr)
            return 2
        if args.chip8_demo_check:
            from .offline_chip8_preview import verify_native_chip8_player
            try:
                report = verify_native_chip8_player()
            except (ValueError, RuntimeError, OSError) as exc:
                print("native CHIP-8 game check rejected: " + str(exc), file=sys.stderr)
                return 1
            if args.json_output:
                print(json.dumps(report, sort_keys=True))
            else:
                print("Original CHIP-8 ROM: actually executed to WIN on built-in VM")
            return 0
        from scripts.game.export_chip8 import main as export_chip8
        flags = (
            ["--demo-rom", "--output", args.chip8_demo_output]
            if args.chip8_demo_output is not None
            else [
                "--capsule", args.chip8_export_capsule,
                "--output", args.chip8_rom_output,
            ]
        )
        return export_chip8(flags)
    if args.game_project is not None and not (args.game_preview or args.game_preview_check):
        print("--game-project requires --game-preview or --game-preview-check", file=sys.stderr)
        return 2
    if args.game_project is not None and args.game_seed is not None:
        print("--game-project and --game-seed are mutually exclusive", file=sys.stderr)
        return 2
    if args.game_seed is not None and not (args.game_preview or args.game_preview_check):
        print("--game-seed requires --game-preview or --game-preview-check", file=sys.stderr)
        return 2
    if args.game_preview_check:
        if (
            args.model or args.deployment or args.prompt or args.backup_in
            or args.backup_out or args.workspace or args.native_smoke
            or args.doctor or args.qualify_model or args.library
            or args.use_library or library_mode or queue_mode or snapshot_mode
            or audit_mode or args.queue_db or args.queue_library
            or args.snapshot_workspace or args.snapshot_library
            or args.snapshot_queue
        ):
            print("headless game check cannot combine with model or state actions",
                  file=sys.stderr)
            return 2
        from .offline_game_preview import DEFAULT_SEED, verify_game_preview, load_game_project
        try:
            tiles = load_game_project(args.game_project) if args.game_project else None
            report = verify_game_preview(
                seed=DEFAULT_SEED if args.game_seed is None else args.game_seed,
                **({"project_tiles": tiles} if tiles is not None else {}),
            )
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            print(
                "native game replay verification rejected: "
                + type(exc).__name__ + ": " + str(exc),
                file=sys.stderr,
            )
            return 1
        if args.json_output:
            print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        else:
            print(
                "Native gameplay replay VERIFIED: "
                + str(report["frames_verified"]) + " frames; "
                "desktop rendering NOT verified"
            )
        return 0

    if args.game_preview:
        if (
            args.model or args.deployment or args.prompt or args.backup_in
            or args.backup_out or args.workspace or args.native_smoke
            or args.doctor or args.qualify_model or args.library
            or args.use_library or library_mode or queue_mode or snapshot_mode
            or audit_mode or args.queue_db or args.queue_library
            or args.snapshot_workspace or args.snapshot_library
            or args.snapshot_queue or args.json_output
        ):
            print("native game preview must run without model, state or JSON modes",
                  file=sys.stderr)
            return 2
        from .offline_game_preview import DEFAULT_SEED, run_game_preview, load_game_project
        try:
            tiles = load_game_project(args.game_project) if args.game_project else None
            return run_game_preview(
                seed=DEFAULT_SEED if args.game_seed is None else args.game_seed,
                **({"project_tiles": tiles} if tiles is not None else {}),
            )
        except (ValueError, RuntimeError, OSError, ImportError) as exc:
            print(
                "native offline game preview unavailable: "
                + type(exc).__name__ + ": " + str(exc),
                file=sys.stderr,
            )
            return 1

    if args.capability_file is not None or args.capability_graph_file is not None or args.capability_list:
        # Model-free deterministic engine is strictly separate from all state,
        # network, training, inference and OS-permission controls.
        if (
            args.model or args.deployment or args.prompt or args.backup_in
            or args.backup_out or args.workspace or args.native_smoke
            or args.doctor or args.qualify_model or args.library
            or args.use_library or library_mode or queue_mode
            or snapshot_mode or audit_mode or args.queue_db
            or args.queue_library or args.snapshot_workspace
            or args.snapshot_library or args.snapshot_queue
        ):
            print("deterministic capabilities cannot be combined with model or state actions", file=sys.stderr)
            return 2
        from skeleton.ai.runtime.deterministic_capabilities import (
            CapabilityTaskError, MAX_INPUT_BYTES, OPERATIONS,
            execute_capability_json,
        )
        from skeleton.ai.runtime.capability_graph import (
            MAX_GRAPH_BYTES, execute_capability_graph_json,
        )
        try:
            if args.capability_list:
                report = {
                    "schema_version": "skeleton.offline_deterministic_capabilities.catalog.v1",
                    "operations": sorted(OPERATIONS),
                    "model_inference_required": False,
                    "training_examples_required": 0,
                    "executor_authority_granted": False,
                }
            else:
                selected = Path(
                    args.capability_graph_file or args.capability_file
                ).expanduser()
                if selected.is_symlink() or not selected.is_file():
                    raise CapabilityTaskError("selected task must be a regular local file")
                limit = MAX_GRAPH_BYTES if args.capability_graph_file else MAX_INPUT_BYTES
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(selected, flags)
                with os.fdopen(fd, "rb") as handle:
                    meta = os.fstat(handle.fileno())
                    if not stat.S_ISREG(meta.st_mode) or meta.st_size > limit:
                        raise CapabilityTaskError("selected task is not a bounded regular file")
                    raw = handle.read(limit + 1)
                report = (
                    execute_capability_graph_json(raw)
                    if args.capability_graph_file else execute_capability_json(raw)
                )
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            print(f"deterministic capability rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if args.json_output or args.capability_list:
            print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        else:
            print(json.dumps(report.get("result", report.get("outputs")), sort_keys=True, ensure_ascii=False))
        return 0

    if not queue_mode and (args.queue_db or args.queue_library):
        print("queue database paths require a queue operation", file=sys.stderr)
        return 2
    if not snapshot_mode and (
        args.snapshot_workspace or args.snapshot_library or args.snapshot_queue
    ):
        print("snapshot database paths require a snapshot operation", file=sys.stderr)
        return 2
    if snapshot_mode and audit_mode:
        print("snapshots and read-only audits must be invoked separately", file=sys.stderr)
        return 2
    if queue_mode and audit_mode:
        print("queue mutation and data audits must be invoked separately", file=sys.stderr)
        return 2
    if snapshot_mode:
        actions = sum(bool(x) for x in (
            args.snapshot_to, args.restore_from, args.verify_snapshot,
        ))
        if (
            actions != 1 or args.qualify_model or args.model or args.deployment or args.prompt
            or args.backup_in or args.backup_out or args.workspace
            or args.doctor or args.native_smoke or library_mode
            or queue_mode or args.use_library or args.library or args.queue_db
            or (args.verify_snapshot and (
                args.snapshot_workspace or args.snapshot_library or args.snapshot_queue
            ))
        ):
            print("snapshot operations require one action without inference or queue options", file=sys.stderr)
            return 2
        paths = {
            "workspace": args.snapshot_workspace,
            "library": args.snapshot_library,
            "queue": args.snapshot_queue,
        }
        try:
            if args.snapshot_to:
                report = create_snapshot(args.snapshot_to, **paths)
                action = "created"
            elif args.restore_from:
                report = restore_snapshot(args.restore_from, **paths)
                action = "restored"
            else:
                report = verify_snapshot(args.verify_snapshot)
                action = "verified"
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"offline recovery rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        response = {
            "schema_version": "skeleton.app.offline_snapshot.command.v1",
            "action": action, "manifest": report,
        }
        if args.json_output:
            print(json.dumps(response, sort_keys=True, ensure_ascii=False))
        else:
            print(f"Offline snapshot {action}: {len(report['databases'])} local databases")
        return 0

    if audit_mode:
        if (
            args.qualify_model or args.native_smoke or args.doctor or snapshot_mode or library_mode
            or queue_mode or args.model or args.deployment or args.prompt
            or args.backup_in or args.backup_out or args.workspace
            or args.library or args.use_library or args.queue_db
            or args.snapshot_workspace or args.snapshot_library or args.snapshot_queue
        ):
            print("local semantic audits cannot be combined with inference or mutation", file=sys.stderr)
            return 2
        try:
            reports = {
                kind: audit_database(path, kind)
                for kind, path in audits.items() if path is not None
            }
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"offline audit rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        output = {
            "schema_version": "skeleton.app.offline_audit.command.v1",
            "ok": True,
            "reports": reports,
        }
        if args.json_output:
            print(json.dumps(output, sort_keys=True, ensure_ascii=False))
        else:
            print("Offline state integrity PASS: " + ", ".join(sorted(reports)))
        return 0

    if args.qualify_model:
        if (
            not (args.model or args.deployment) or args.doctor
            or args.native_smoke or args.prompt or args.backup_in
            or args.backup_out or args.workspace or args.library
            or args.use_library or library_mode or queue_mode
            or snapshot_mode or audit_mode or args.queue_db
        ):
            print("model qualification requires one local model without other operations", file=sys.stderr)
            return 2
        from .offline_qualification import qualify_offline_model
        try:
            report = qualify_offline_model(
                model=args.model, deployment=args.deployment,
                max_output_tokens=args.max_output_tokens,
            )
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            print(f"local model qualification rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        else:
            print(
                "Local qualification PASS: 2 bound inference turns with "
                "session reopen; OS network isolation NOT VERIFIED"
            )
        return 0

    if args.native_smoke and args.doctor:
        print("--native-smoke and --doctor are mutually exclusive", file=sys.stderr)
        return 2
    if queue_mode:
        if (
            args.qualify_model or
            not args.queue_db or args.model or args.deployment or args.prompt
            or args.backup_in or args.backup_out or args.workspace
            or args.doctor or args.native_smoke or library_mode
            or args.use_library or args.library or args.snapshot_workspace
            or args.snapshot_library or args.snapshot_queue
            or (bool(args.enqueue_dir) != bool(args.queue_library))
            or (args.cancel_queue_job and args.retry_queue_job)
            or (args.cancel_queue_job and (args.enqueue_dir or args.run_queue))
            or (args.retry_queue_job and (args.enqueue_dir or args.run_queue))
            or type(args.drain_limit) is not int
            or not 1 <= args.drain_limit <= 20
        ):
            print("invalid offline queue arguments; select explicit local queue and index paths", file=sys.stderr)
            return 2
        try:
            with OfflineIndexQueue(args.queue_db) as queue:
                enqueued = (
                    queue.enqueue(args.enqueue_dir, args.queue_library)
                    if args.enqueue_dir else None
                )
                changed = (
                    queue.cancel(args.cancel_queue_job)
                    if args.cancel_queue_job else
                    queue.retry(args.retry_queue_job)
                    if args.retry_queue_job else None
                )
                processed = queue.drain(limit=args.drain_limit) if args.run_queue else ()
                jobs = queue.list_jobs() if args.queue_status else ()
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"offline indexing queue rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        output = {
            "schema_version": "skeleton.app.offline_index_queue.command.v1",
            "enqueued": enqueued.to_dict() if enqueued else None,
            "updated": changed.to_dict() if changed else None,
            "processed": [job.to_dict() for job in processed],
            "jobs": [job.to_dict() for job in jobs],
        }
        if args.json_output:
            print(json.dumps(output, sort_keys=True, ensure_ascii=False))
        else:
            print(f"Offline queue: {len(processed)} processed, {len(jobs)} listed")
            for job in processed:
                print(f"{job.job_id}: {job.state}, attempt {job.attempts}")
        return 0 if all(job.state == "completed" for job in processed) else 1

    if library_mode:
        if (
            args.qualify_model or
            args.doctor or args.native_smoke or args.model or args.deployment
            or args.prompt or args.backup_in or args.backup_out
            or args.workspace or args.use_library or not args.library
            or args.queue_db or args.queue_library
        ):
            print("library indexing/search requires --library, without model or inference options", file=sys.stderr)
            return 2
        try:
            with OfflineDocumentLibrary(args.library) as documents:
                indexed = documents.index_directory(args.index_dir) if args.index_dir else None
                hits = documents.search(args.search, limit=args.context_limit) if args.search else ()
                count = documents.count()
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"offline library rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        response = {
            "schema_version": "skeleton.app.offline_library.command.v1",
            "indexed": indexed,
            "document_count": count,
            "results": [hit.to_dict() for hit in hits],
        }
        if args.json_output:
            print(json.dumps(response, sort_keys=True, ensure_ascii=False))
        else:
            print(f"Local documents indexed: {count}")
            for hit in hits:
                print(f"[{hit.relative_path}] {hit.excerpt}")
        return 0

    if args.native_smoke:
        if (
            args.qualify_model or
            args.model or args.deployment or args.prompt or
            args.backup_in or args.backup_out or args.workspace or
            args.library or args.use_library or args.queue_db
        ):
            print("native smoke does not accept model, prompt or backup parameters", file=sys.stderr)
            return 2
        try:
            ok = smoke_offline_native_inference()
        except Exception as exc:
            print(f"native inference smoke failed: {type(exc).__name__}", file=sys.stderr)
            return 1
        print("Native inference graph: PASS" if ok else "Native inference graph: FAIL")
        return 0 if ok else 1

    if args.doctor:
        if (
            args.qualify_model or
            not (args.model or args.deployment) or args.prompt or
            args.backup_in or args.backup_out or args.workspace or
            args.library or args.use_library or args.queue_db
        ):
            print("--doctor requires one local model without generation or storage options", file=sys.stderr)
            return 2
        try:
            report = inspect_local_readiness(model=args.model, deployment=args.deployment)
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            print(f"offline readiness rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        else:
            print(
                "Local artifact: VERIFIED; inference/network isolation: NOT TESTED; "
                "model " + report["model_digest"][:16]
            )
        return 0

    if args.queue_db or args.queue_library:
        print("model inference cannot use local queue management flags", file=sys.stderr)
        return 2
    if not (args.model or args.deployment) or not args.prompt:
        print("local inference requires --prompt and either --model or --deployment", file=sys.stderr)
        return 2

    if args.workspace and args.backup_in:
        print("--backup-in cannot be combined with a revisioned workspace", file=sys.stderr)
        return 2
    if bool(args.library) != bool(args.use_library):
        print("contextual inference requires both --library and --use-library", file=sys.stderr)
        return 2
    if type(args.context_limit) is not int or not 1 <= args.context_limit <= 20:
        print("context limit must be between 1 and 20", file=sys.stderr)
        return 2
    durable = None
    hits = ()
    try:
        session = (
            OfflineGGUFSession(args.deployment)
            if args.deployment is not None
            else OfflineAISession(load_native_checkpoint(args.model))
        )
        if args.workspace:
            durable = DurableOfflineSession(session, args.workspace, session_id=args.session_id)
        elif args.backup_in is not None:
            session.restore_history_backup(args.backup_in)
        inference_prompt = args.prompt
        if args.use_library:
            with OfflineDocumentLibrary(args.library) as documents:
                hits = documents.search(args.prompt, limit=args.context_limit)
            inference_prompt = render_local_context(args.prompt, hits)
        answer = asyncio.run(
            (durable or session).ask(
                args.prompt,
                max_output_tokens=args.max_output_tokens,
                inference_prompt=inference_prompt if args.use_library else None,
            )
        )
        if args.backup_out is not None:
            session.save_history_backup(args.backup_out)
    except (ValueError, RuntimeError, OSError, TypeError) as exc:
        print(f"local inference rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if durable is not None:
            durable.close()

    if args.json_output:
        print(json.dumps({
            "schema_version": 1,
            "text": answer.text,
            "model_digest": answer.model_digest,
            "execution_receipt_digest": answer.execution_receipt_digest,
            "input_tokens": answer.input_tokens,
            "output_tokens": answer.output_tokens,
            "retrieved_sources": [
                {"relative_path": hit.relative_path, "sha256": hit.document_sha256}
                for hit in hits
            ],
        }, sort_keys=True, ensure_ascii=False))
    else:
        print(answer.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
