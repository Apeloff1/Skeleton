"""Fail CI when Git-tracked text files contain high-confidence secret material.

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
import subprocess
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
# Large checked-in machine indexes can exceed 16 MiB on a legacy single line.
# Keep the reader bounded while scanning those tracked text corpora in full.
# Producers are separately required to emit bounded physical lines; this 64 MiB
# ceiling preserves fail-closed coverage for already-materialized legacy data.
MAX_FILE_BYTES = 64 * 1024 * 1024
SCAN_FRAGMENT_CHARS = 1024 * 1024
SCAN_OVERLAP_CHARS = 1024
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
    """Yield Git-tracked text candidates with bounded, fail-closed discovery.

    Security scanning is concerned with material that can land in the repository.
    Enumerating the Git index avoids recursively walking generated CI workspace
    state while preserving coverage of every tracked candidate. Index discovery
    itself is fail closed: an unavailable or malformed repository cannot silently
    produce an empty scan.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError("tracked-file enumeration failed") from exc

    if completed.returncode != 0:
        raise OSError("tracked-file enumeration failed")

    root = REPO_ROOT.resolve()
    for raw_relative in completed.stdout.split(b"\0"):
        if not raw_relative:
            continue
        relative_text = os.fsdecode(raw_relative)
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise OSError("tracked-file enumeration produced an unsafe path")
        if any(part in SKIP_DIRS for part in relative.parts[:-1]):
            continue

        path = root / relative
        try:
            metadata = path.lstat()
        except OSError:
            # Preserve fail-closed handling in ``violations`` for tracked paths
            # whose checkout metadata cannot be read.
            yield path
            continue

        # A tracked symlink's target is not repository file content and following
        # it could escape the trusted checkout. Gitlink/directories are likewise
        # outside this file scanner's responsibility.
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            continue
        if not _is_text_candidate(path):
            continue
        yield path


def _is_placeholder(candidate: str) -> bool:
    lowered = candidate.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _scan_secret_fragment(text: str, label: Path, number: int) -> list[str]:
    """Scan one bounded text fragment without echoing candidate material."""

    findings: list[str] = []
    specific_finding = False
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if _is_placeholder(match.group(0)):
                continue
            findings.append(f"{label}:{number}: possible {name}")
            specific_finding = True
            break
    if specific_finding:
        return findings

    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        candidate = match.group("value")
        if _looks_like_high_entropy_secret(candidate):
            findings.append(
                f"{label}:{number}: possible high-entropy secret-like assignment"
            )
            break
    return findings


def violations(path: Path) -> list[str]:
    try:
        label = path.relative_to(REPO_ROOT)
    except ValueError:
        label = path

    findings: list[str] = []
    try:
        # Scan arbitrarily long logical lines in bounded character fragments.
        # The overlap preserves credential patterns that straddle fragment
        # boundaries without exempting generated/minified one-line artifacts.
        with path.open("r", encoding="utf-8", newline="") as handle:
            number = 1
            carry = ""
            logical_line_bytes = 0
            while True:
                fragment = handle.readline(SCAN_FRAGMENT_CHARS)
                if not fragment:
                    break

                # A tracked machine artifact may contain a very long logical
                # line. Keep scanning bounded and fail closed instead of
                # silently exempting material beyond the configured byte cap.
                logical_line_bytes += len(fragment.encode("utf-8"))
                if logical_line_bytes > MAX_FILE_BYTES:
                    return [
                        f"{label}:{number}: scan failure: exceeds "
                        f"{MAX_FILE_BYTES}-byte secret-scan line limit"
                    ]

                combined = carry + fragment
                findings.extend(_scan_secret_fragment(combined, label, number))

                continued = (
                    len(fragment) >= SCAN_FRAGMENT_CHARS
                    and not fragment.endswith("\n")
                    and not fragment.endswith("\r")
                )
                if continued:
                    carry = combined[-SCAN_OVERLAP_CHARS:]
                else:
                    carry = ""
                    logical_line_bytes = 0
                    number += 1
    except UnicodeError as exc:
        return [f"{label}: read failure: {type(exc).__name__}"]
    except OSError as exc:
        return [f"{label}: read failure: {type(exc).__name__}"]

    return list(dict.fromkeys(findings))


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
        findings.append("scanner coverage failure: no Git-tracked text files were scanned")

    if findings:
        print("Potential committed secrets detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        print(
            "Do not paste secret values into CI logs. Revoke and rotate confirmed credentials.",
            file=sys.stderr,
        )
        return 1
    print(f"Secret hygiene gate passed across {scanned} Git-tracked text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
