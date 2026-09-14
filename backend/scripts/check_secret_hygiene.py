"""Fail CI when tracked text files contain high-confidence secret material.

This repository-native gate intentionally focuses on patterns with low false
positive rates so it can run on every pull request without external services.
It complements platform secret scanning; it does not replace history scanning
or credential rotation after a confirmed exposure.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".expo",
    "__pycache__",
}
MAX_FILE_BYTES = 2 * 1024 * 1024
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".env", ".example", ".md",
    ".txt", ".sh", ".ps1", ".bat", ".xml", ".html", ".css",
}

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "GitHub token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    ),
    (
        "GitHub fine-grained token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,255}\b"),
    ),
    (
        "AWS access key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "Slack token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ),
    (
        "OpenAI-style API key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    ),
    (
        "credential-bearing database URI",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
    ),
)

PLACEHOLDER_MARKERS = (
    "example",
    "placeholder",
    "changeme",
    "change-me",
    "your_",
    "your-",
    "dummy",
    "not-a-real",
    "redacted",
)


def candidate_files() -> Iterable[Path]:
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        if path.name.startswith(".env") or path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def _is_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []

    try:
        label = path.relative_to(REPO_ROOT)
    except ValueError:
        label = path

    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if _is_placeholder(line):
            continue
        for name, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(f"{label}:{number}: possible {name}")
    return findings


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in candidate_files():
        scanned += 1
        findings.extend(violations(path))
    if findings:
        print("Potential committed secrets detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        print("Do not paste secret values into CI logs. Rotate confirmed credentials.", file=sys.stderr)
        return 1
    print(f"Secret hygiene gate passed across {scanned} tracked-style text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
