#!/usr/bin/env python3
"""Run executable standalone-AI system qualification and emit exact-head evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--evidence-out", default=None)
    parser.add_argument("--print-evidence", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> dict[str, object]:
    from skeleton.ai.evaluation.system_qualification import (  # noqa: PLC0415
        qualify_system_completion,
    )

    head_sha = (args.head_sha or _git_head()).strip()
    if _GIT_SHA.fullmatch(head_sha) is None:
        raise ValueError("head_sha must be a lowercase 40-character git sha")

    if args.workdir:
        workdir = Path(args.workdir)
        if not workdir.is_absolute():
            workdir = ROOT / workdir
        receipt = await qualify_system_completion(
            workdir,
            source_revision=head_sha,
        )
        return receipt.as_dict()

    with tempfile.TemporaryDirectory(prefix="ai-system-qualification-") as temp:
        receipt = await qualify_system_completion(
            temp,
            source_revision=head_sha,
        )
        return receipt.as_dict()


def main(argv: list[str] | None = None) -> int:
    args = _args(list(sys.argv[1:] if argv is None else argv))
    try:
        receipt = asyncio.run(_run(args))
    except Exception as exc:
        print(f"ERROR: system qualification failed: {exc}", file=sys.stderr)
        return 1

    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        output = Path(args.evidence_out)
        if not output.is_absolute():
            output = ROOT / output
        output.write_text(encoded, encoding="utf-8")
    if args.print_evidence:
        print(encoded, end="")

    if receipt.get("valid") is not True:
        report = receipt.get("report")
        if isinstance(report, dict):
            print(
                "ERROR: completion report invalid; "
                f"missing={report.get('missing')} failed={report.get('failed')}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
