"""Fail CI when tracked-style text files contain high-confidence secret material.

This repository-native gate intentionally focuses on patterns with low false
positive rates so it can run on every pull request without external services.
It complements Gitleaks history scanning; it does not replace credential
rotation after a confirmed exposure.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import stat
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
        "GitLab personal access token",
        re.compile(r"\bglpat-[A-Za-z0-9_-]{20,255}\b"),
    ),
    (
        "npm access token",
        re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    ),
    (
        "PyPI API token",
        re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{40,255}\b"),
    ),
    (
        "AWS access key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "AWS secret access key",
        re.compile(
            r"\bAWS_SECRET_ACCESS_KEY\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}[\"']?",
            re.IGNORECASE,
        ),
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
        "Stripe live secret key",
        re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    ),
    (
        "Google API key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
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
    # Canonical documentation-only database credentials. Keep these narrow:
    # matching is applied to the credential-shaped candidate, not the full line.
    "user:pass@",
    "username:password@",
)

# Provider-specific regexes catch known token formats above. This second layer
# catches unknown/provider-neutral credentials only when both the assignment
# name and the value are strongly secret-shaped, keeping the gate low-noise.
SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    ["']?
    (?P<name>
        api[_-]?key
        | access[_-]?token
        | auth[_-]?token
        | client[_-]?secret
        | private[_-]?token
        | secret[_-]?key
        | password
        | passwd
    )
    ["']?
    \s*[:=]\s*
    ["']?
    (?P<value>[A-Za-z0-9][A-Za-z0-9._~+/=!@#$%^&*-]{27,})
    ["']?
    """,
)
HIGH_ENTROPY_MIN_BITS_PER_CHAR = 4.2
HIGH_ENTROPY_MIN_UNIQUE_RATIO = 0.35


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    length = len(value)
    counts: dict[str, int] = {}
    for character in value:
        counts[character] = counts.get(character, 0) + 1
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def _looks_like_high_entropy_secret(value: str) -> bool:
    if _is_placeholder(value):
        return False
    if len(set(value)) / len(value) < HIGH_ENTROPY_MIN_UNIQUE_RATIO:
        return False
    character_classes = sum(
        (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
            any(not character.isalnum() for character in value),
        )
    )
    # Long hexadecimal/base-N credentials may legitimately use only two
    # character classes; shorter generic values need three to stay low-noise.
    minimum_classes = 2 if len(value) >= 40 else 3
    return (
        character_classes >= minimum_classes
        and _shannon_entropy(value) >= HIGH_ENTROPY_MIN_BITS_PER_CHAR
    )


def _is_text_candidate(path: Path) -> bool:
    return path.name.startswith(".env") or path.suffix.lower() in TEXT_SUFFIXES


def candidate_files() -> Iterable[Path]:
    """Yield bounded text candidates without hiding traversal or metadata loss.

    Directory enumeration uses ``os.scandir`` instead of ``Path.rglob`` so an
    unreadable subtree raises into ``main`` and blocks the gate. Symlinks are not
    followed. If metadata for an entry cannot be read, that path is still yielded
    so ``violations`` produces a sanitized fail-closed finding.
    """
    pending = [REPO_ROOT]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if path.name in SKIP_DIRS:
                    continue
                try:
                    metadata = path.lstat()
                except OSError:
                    yield path
                    continue
                if stat.S_ISLNK(metadata.st_mode):
                    continue
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(path)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                if not _is_text_candidate(path):
                    continue
                # Oversized tracked-style candidates must still reach the
                # bounded reader. Silently skipping them lets file padding
                # suppress secret scanning.
                yield path


def _is_placeholder(candidate: str) -> bool:
    lowered = candidate.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def violations(path: Path) -> list[str]:
    try:
        label = path.relative_to(REPO_ROOT)
    except ValueError:
        label = path

    try:
        # Bound the actual read as well as discovery-time metadata. This keeps a
        # stat failure or size-change race from turning secret scanning into an
        # unbounded memory read.
        with path.open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        return [f"{label}: read failure: {type(exc).__name__}"]

    if len(raw) > MAX_FILE_BYTES:
        return [
            f"{label}: scan failure: exceeds {MAX_FILE_BYTES}-byte secret-scan limit"
        ]

    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        # Never echo raw decoder text/bytes into CI logs.
        return [f"{label}: read failure: {type(exc).__name__}"]

    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        specific_finding = False
        for name, pattern in PATTERNS:
            for match in pattern.finditer(line):
                # Suppress only an explicitly placeholder-shaped credential,
                # never an entire source line. Otherwise a real credential can
                # evade scanning simply by appending "# example" or similar.
                if _is_placeholder(match.group(0)):
                    continue
                findings.append(f"{label}:{number}: possible {name}")
                specific_finding = True
                break
        if specific_finding:
            continue

        for match in SECRET_ASSIGNMENT_RE.finditer(line):
            candidate = match.group("value")
            if _looks_like_high_entropy_secret(candidate):
                findings.append(
                    f"{label}:{number}: possible high-entropy secret-like assignment"
                )
                break
    return findings


def main() -> int:
    findings: list[str] = []
    scanned = 0
    try:
        for path in candidate_files():
            scanned += 1
            findings.extend(violations(path))
    except OSError as exc:
        findings.append(f"repository traversal failure: {type(exc).__name__}")

    if scanned == 0:
        findings.append("scanner coverage failure: no tracked-style text files were scanned")

    if findings:
        print("Potential committed secrets detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        print(
            "Do not paste secret values into CI logs. Revoke and rotate confirmed credentials.",
            file=sys.stderr,
        )
        return 1
    print(f"Secret hygiene gate passed across {scanned} tracked-style text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
