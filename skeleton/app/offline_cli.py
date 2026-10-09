"""Self-contained offline inference CLI for frozen Windows/Linux executables.

This is an application entrypoint, not a new inference owner. It uses only
operator-supplied local model artifacts through the existing canonical
native and llama.cpp engine adapters. No model is fetched or generated.
"""
from __future__ import annotations

import argparse
import asyncio
import json
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
            actions != 1 or args.model or args.deployment or args.prompt
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
            args.native_smoke or args.doctor or snapshot_mode or library_mode
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

    if args.native_smoke and args.doctor:
        print("--native-smoke and --doctor are mutually exclusive", file=sys.stderr)
        return 2
    if queue_mode:
        if (
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
