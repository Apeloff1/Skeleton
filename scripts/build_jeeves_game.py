#!/usr/bin/env python3
"""Operator compatibility CLI over the canonical local Jeeves game operation."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from skeleton.app.offline_game_builder import (
    SCHEMA, SYSTEM, POLICY_ID, PROPOSAL_SCHEMA, admit_proposal,
    propose, publish_create_only, qualify_interactive, run_local_game_build,
)


def execute(args: argparse.Namespace):
    from skeleton.app.local_ai import load_gguf_deployment, private_desktop_database
    if args.report and (args.report.exists() or args.report.is_symlink()):
        raise ValueError("choose a new report file")
    backend = load_gguf_deployment(args.manifest)
    workspace = args.workspace_database or private_desktop_database(backend.model_digest)
    return run_local_game_build(
        backend, args.brief, args.out, workspace_database=workspace,
        output_tokens=args.output_tokens, planning_timeout=args.planning_timeout,
        deadline=args.deadline, repair=not args.no_repair,
        require_model=args.require_model, playtest=args.playtest,
    )

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workspace-database", type=Path,
                        help="existing local workspace lease namespace; conversation content is not changed")
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--planning-timeout", type=int, default=90)
    parser.add_argument("--deadline", type=int, default=180)
    parser.add_argument("--no-repair", action="store_true")
    parser.add_argument("--require-model", action="store_true")
    parser.add_argument("--playtest", choices=("off", "auto", "require"), default="require")
    args = parser.parse_args(argv)
    try:
        report = execute(args)
        encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.report:
            descriptor = os.open(args.report,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded)
        print(encoded, end="")
        return 0 if report["ok"] else 1
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "error": "local_game_build_rejected"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
