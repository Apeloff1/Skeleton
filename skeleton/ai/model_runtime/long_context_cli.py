"""Operator CLI for offline token custody; never starts model inference."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .long_context_spool import LongContextSpool, LongContextSpoolError, read_selected_sequence
from .tokenization import deserialize_token_sequence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verified offline token spool")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--tokenizer-digest", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="Store canonical serialized TokenSequence")
    stage.add_argument("--sequence-file", type=Path, required=True)
    inspect = commands.add_parser("inspect", help="Verify a persisted checkpoint")
    inspect.add_argument("--checkpoint", required=True)
    window = commands.add_parser("window", help="Read next bounded token window")
    window.add_argument("--checkpoint", required=True)
    window.add_argument("--max-tokens", type=int, required=True)
    advance = commands.add_parser("advance", help="Persist completed token progress")
    advance.add_argument("--checkpoint", required=True)
    advance.add_argument("--consumed-tokens", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        spool = LongContextSpool(args.root)
        if args.command == "stage":
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
                      "checkpoint": spool.advance(args.checkpoint,
                          expected_tokenizer_digest=args.tokenizer_digest,
                          consumed_tokens=args.consumed_tokens)}
        elif args.command == "inspect":
            checkpoint, sequence = spool.load(
                args.checkpoint, expected_tokenizer_digest=args.tokenizer_digest)
            result = {"schema": "skeleton.ai.long-context-cli.v1",
                      "checkpoint": asdict(checkpoint),
                      "total_tokens": len(sequence.token_ids)}
        else:
            item = spool.next_window(args.checkpoint,
                expected_tokenizer_digest=args.tokenizer_digest,
                max_tokens=args.max_tokens)
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
