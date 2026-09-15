#!/usr/bin/env python3
"""Fail CI on high-confidence credential material in tracked text files.

The scanner intentionally uses conservative, provider-specific signatures instead
of generic entropy heuristics so it can be required on every pull request without
creating an unbounded false-positive waiver culture.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 5 * 1024 * 1024

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{40,255})\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("stripe-live-secret", re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b")),
)


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [ROOT / raw.decode("utf-8") for raw in completed.stdout.split(b"\0") if raw]


def findings_for(path: Path) -> list[tuple[int, str]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot read tracked file {path}: {exc}") from exc

    if len(data) > MAX_TEXT_BYTES or b"\0" in data:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS:
            if pattern.search(line):
                findings.append((line_number, name))
    return findings


def main() -> int:
    failures: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        for line_number, kind in findings_for(path):
            failures.append(f"{relative}:{line_number}: {kind}")

    if failures:
        print("High-confidence secret material detected in tracked files:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("Remove/rotate the credential; do not suppress this required check.", file=sys.stderr)
        return 1

    print(f"Secret scan passed: {len(tracked_files())} tracked files checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
