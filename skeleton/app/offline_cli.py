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
    parser.add_argument(
        "--native-smoke", action="store_true",
        help="run a small locally constructed test model (NOT a trained assistant)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    library_mode = args.index_dir is not None or args.search is not None
    if args.native_smoke and args.doctor:
        print("--native-smoke and --doctor are mutually exclusive", file=sys.stderr)
        return 2
    if library_mode:
        if (
            args.doctor or args.native_smoke or args.model or args.deployment
            or args.prompt or args.backup_in or args.backup_out
            or args.workspace or args.use_library or not args.library
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
            args.library or args.use_library
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
            args.library or args.use_library
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
            (durable or session).ask(inference_prompt, max_output_tokens=args.max_output_tokens)
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
