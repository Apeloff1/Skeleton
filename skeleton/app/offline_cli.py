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
    parser.add_argument(
        "--native-smoke", action="store_true",
        help="run a small locally constructed test model (NOT a trained assistant)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.native_smoke:
        if (
            args.model or args.deployment or args.prompt or
            args.backup_in or args.backup_out or args.workspace
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

    if not (args.model or args.deployment) or not args.prompt:
        print("local inference requires --prompt and either --model or --deployment", file=sys.stderr)
        return 2

    if args.workspace and args.backup_in:
        print("--backup-in cannot be combined with a revisioned workspace", file=sys.stderr)
        return 2
    durable = None
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
        answer = asyncio.run(
            (durable or session).ask(args.prompt, max_output_tokens=args.max_output_tokens)
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
        }, sort_keys=True, ensure_ascii=False))
    else:
        print(answer.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
