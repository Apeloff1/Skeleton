"""Explicit operator harness for the canonical *real* GGUF cold-reopen test.

Never implement a parallel acceptance path here: the native laptop CLI owns
installed-source/rights checks, two isolated GGUF activations, canonical
SQLite replay, nonretrying uncertainty and bounded live JSONL publication.
This adapter exists only to preserve the long-standing operator command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main as native_cli
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation


class _PrivateArgs(argparse.ArgumentParser):
    """Do not echo an untrusted command-line value or private local path."""

    def error(self, message: str) -> None:
        raise ContractViolation("invalid native laptop acceptance arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _PrivateArgs(description="Live installed GGUF + cold SQLite replay", allow_abbrev=False)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--capacity-root", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--inference-ms", type=int, default=90000)
    parser.add_argument("--capacity-slots", type=int, default=1)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--prompt-stdin", action="store_true", required=True)
    parser.add_argument("--approve-real-model-test", action="store_true", required=True)
    return parser


def main(argv=None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.prompt_stdin is not True or args.approve_real_model_test is not True:
            raise ContractViolation("explicit native test and private stdin required")
        # Do not read, strip, decode, repeat or log the prompt here. The
        # authoritative CLI enforces exact UTF-8 and its 32KiB input ceiling.
        # It must run both native startup/rights audits and the second
        # independently activated source-fenced cold SQLite replay.
        passed = [
            "--mode", "cold-reopen",
            "--approve-real-acceptance",
            "--prompt-stdin",
            "--model-root", str(args.model_root),
            "--state-dir", str(args.state_dir),
            "--capacity-root", str(args.capacity_root),
            "--tenant", args.tenant,
            "--subject", args.subject,
            "--context", str(args.context),
            "--max-new-tokens", str(args.max_new_tokens),
            "--threads", str(args.threads),
            "--gpu-layers", str(args.gpu_layers),
            "--inference-ms", str(args.inference_ms),
            "--capacity-slots", str(args.capacity_slots),
            "--capacity-budget-bytes", str(args.capacity_budget_bytes),
        ]
        code = native_cli(passed)
        # Synthetic wrappers and truthy bool return codes are not success.
        # This adapter never publishes a second, unfenced success record.
        return 0 if type(code) is int and code == 0 else 2
    except (Exception, KeyboardInterrupt) as exc:
        print(
            json.dumps({"status": "held", "error_class": type(exc).__name__}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
