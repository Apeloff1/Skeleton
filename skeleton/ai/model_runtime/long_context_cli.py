"""Operator CLI for offline token custody; never starts model inference."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .long_context_spool import LongContextSpool, LongContextSpoolError, read_selected_sequence
from .long_context_progress import LongContextProgressHead
from .tokenization import deserialize_token_sequence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verified offline token spool")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--tokenizer-digest", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="Store canonical serialized TokenSequence")
    stage.add_argument("--sequence-file", type=Path, required=True)
    inspect = commands.add_parser("inspect", help="Verify a persisted checkpoint")
    audit = commands.add_parser("audit", help="Verify bounded checkpoint ancestry to genesis")
    audit.add_argument("--checkpoint", required=True)
    audit.add_argument("--max-checkpoints", type=int, default=4096)
    inspect.add_argument("--checkpoint", required=True)
    window = commands.add_parser("window", help="Read next bounded token window")
    window.add_argument("--checkpoint", required=True)
    window.add_argument("--max-tokens", type=int, required=True)
    window.add_argument("--max-checkpoints", type=int, default=4096)
    advance = commands.add_parser("advance", help="Persist completed token progress")
    advance.add_argument("--checkpoint", required=True)
    advance.add_argument("--consumed-tokens", type=int, required=True)
    advance.add_argument("--max-checkpoints", type=int, default=4096)
    status = commands.add_parser("capacity", help="Read bounded payload-free POSIX spool capacity")
    status.add_argument("--request-bytes", type=int, default=0)
    head_init = commands.add_parser("head-init", help="Bind durable stream cursor")
    head_init.add_argument("--stream-id", required=True)
    head_init.add_argument("--checkpoint", required=True)
    head_init.add_argument("--max-checkpoints", type=int, default=4096)
    head_status = commands.add_parser("head-status", help="Verify current stream cursor")
    head_status.add_argument("--stream-id", required=True)
    head_status.add_argument("--max-checkpoints", type=int, default=4096)
    head_window = commands.add_parser("head-window", help="Observe bounded stream window")
    head_window.add_argument("--stream-id", required=True)
    head_window.add_argument("--max-tokens", type=int, required=True)
    head_window.add_argument("--max-checkpoints", type=int, default=4096)
    head_advance = commands.add_parser("head-advance", help="CAS committed progress")
    head_advance.add_argument("--stream-id", required=True)
    head_advance.add_argument("--expected-checkpoint", required=True)
    head_advance.add_argument("--consumed-tokens", type=int, required=True)
    head_advance.add_argument("--max-checkpoints", type=int, default=4096)
    compare_window = commands.add_parser("head-compare-window",
        help="Generation-fenced observation, never an execution lease")
    compare_window.add_argument("--stream-id", required=True)
    compare_window.add_argument("--expected-checkpoint", required=True)
    compare_window.add_argument("--expected-generation", type=int, required=True)
    compare_window.add_argument("--max-tokens", type=int, required=True)
    compare_window.add_argument("--max-checkpoints", type=int, default=4096)
    commit_window = commands.add_parser("head-commit-window",
        help="CAS observed window after separately proven token consumption")
    commit_window.add_argument("--stream-id", required=True)
    commit_window.add_argument("--expected-checkpoint", required=True)
    commit_window.add_argument("--expected-generation", type=int, required=True)
    commit_window.add_argument("--expected-window-digest", required=True)
    commit_window.add_argument("--max-tokens", type=int, required=True)
    commit_window.add_argument("--consumed-tokens", type=int, required=True)
    commit_window.add_argument("--max-checkpoints", type=int, default=4096)
    audit_heads = commands.add_parser("head-audit",
        help="Read-only bounded audit of all local committed heads")
    audit_heads.add_argument("--max-heads", type=int, default=64)
    audit_heads.add_argument("--max-checkpoints", type=int, default=4096)
    commands.add_parser("head-recover", help="Explicit bounded orphan cleanup")
    args = parser.parse_args(argv)
    try:
        spool = LongContextSpool(args.root)
        if args.command.startswith("head-"):
            heads = LongContextProgressHead(spool)
            if args.command == "head-init":
                result = heads.initialize(args.stream_id, args.checkpoint,
                    expected_tokenizer_digest=args.tokenizer_digest,
                    max_checkpoints=args.max_checkpoints)
            elif args.command == "head-status":
                result = heads.status(args.stream_id,
                    expected_tokenizer_digest=args.tokenizer_digest,
                    max_checkpoints=args.max_checkpoints)
            elif args.command == "head-window":
                result = heads.window(args.stream_id,
                    expected_tokenizer_digest=args.tokenizer_digest,
                    max_tokens=args.max_tokens, max_checkpoints=args.max_checkpoints)
            elif args.command == "head-advance":
                result = heads.advance(args.stream_id,
                    expected_checkpoint_digest=args.expected_checkpoint,
                    expected_tokenizer_digest=args.tokenizer_digest,
                    consumed_tokens=args.consumed_tokens,
                    max_checkpoints=args.max_checkpoints)
            elif args.command == "head-compare-window":
                result = heads.compare_window(args.stream_id,
                    expected_checkpoint_digest=args.expected_checkpoint,
                    expected_generation=args.expected_generation,
                    expected_tokenizer_digest=args.tokenizer_digest,
                    max_tokens=args.max_tokens, max_checkpoints=args.max_checkpoints)
            elif args.command == "head-commit-window":
                result = heads.advance_window(args.stream_id,
                    expected_checkpoint_digest=args.expected_checkpoint,
                    expected_generation=args.expected_generation,
                    expected_tokenizer_digest=args.tokenizer_digest,
                    expected_window_digest=args.expected_window_digest,
                    max_tokens=args.max_tokens, consumed_tokens=args.consumed_tokens,
                    max_checkpoints=args.max_checkpoints)
            elif args.command == "head-audit":
                result = heads.audit_inventory(
                    expected_tokenizer_digest=args.tokenizer_digest,
                    max_heads=args.max_heads, max_checkpoints=args.max_checkpoints)
            else:
                result = heads.recover_orphan_temps()
        elif args.command == "capacity":
            result = spool.capacity_snapshot(requested_bytes=args.request_bytes)
        elif args.command == "stage":
            raw = read_selected_sequence(
                args.sequence_file, limit=spool.max_sequence_bytes,
            )
            sequence = deserialize_token_sequence(raw, require_canonical=True)
            if sequence.tokenizer_digest != args.tokenizer_digest:
                raise LongContextSpoolError("tokenizer identity mismatch")
            result = {"schema": "skeleton.ai.long-context-cli.v1",
                      "checkpoint": spool.stage(sequence)}
        elif args.command == "advance":
            result = {"schema": "skeleton.ai.long-context-cli.v1",
                      "checkpoint": spool.audited_advance(args.checkpoint,
                          expected_tokenizer_digest=args.tokenizer_digest,
                          consumed_tokens=args.consumed_tokens,
                          max_checkpoints=args.max_checkpoints)}
        elif args.command == "audit":
            result = spool.audit_history(
                args.checkpoint, expected_tokenizer_digest=args.tokenizer_digest,
                max_checkpoints=args.max_checkpoints,
            )
        elif args.command == "inspect":
            checkpoint, sequence = spool.load(
                args.checkpoint, expected_tokenizer_digest=args.tokenizer_digest)
            result = {"schema": "skeleton.ai.long-context-cli.v1",
                      "checkpoint": asdict(checkpoint),
                      "total_tokens": len(sequence.token_ids)}
        else:
            item = spool.audited_next_window(args.checkpoint,
                expected_tokenizer_digest=args.tokenizer_digest,
                max_tokens=args.max_tokens,
                max_checkpoints=args.max_checkpoints)
            result = {"schema": "skeleton.ai.long-context-cli.v1",
                      "window": None if item is None else {
                          "start": item.start, "stop": item.stop,
                          "token_ids": list(item.token_ids),
                          "source_sequence_digest": item.source_sequence_digest,
                          "digest": item.digest}}
    except (LongContextSpoolError, OSError, ValueError) as exc:
        parser.exit(2, f"long-context-spool: {exc}\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
