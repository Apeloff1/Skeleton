"""Prevent manually dispatched source qualification from running untrusted commits.

These operator workflows execute Python directly from a checked-out repository.
GitHub Actions caches and runner services can be poisoned even when repository
GITHUB_TOKEN permissions are only read-only. Therefore a syntactically valid
caller-selected commit is not an acceptable trust boundary.

Standard-library-only guard; runs in the early workflow input security lane.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
PROTECTED_WORKFLOWS = (
    "godot-provenance-source-qualification.yml",
    "strict-replay-source-qualification.yml",
)
CHECKOUT_RE = re.compile(r"(?m)^ {8}uses: actions/checkout@")
STEP_SPLIT_RE = re.compile(r"(?m)(?=^ {6}- (?:name|uses):)")
PLATFORM_SHA = "${{ github.sha }}"
MAIN_GUARD = "github.repository == 'Apeloff1/Skeleton' && github.ref == 'refs/heads/main'"


def violations_from_text(name: str, source: str) -> list[str]:
    """Require trusted exact-main identity from dispatch to execution."""
    findings: list[str] = []
    if not re.search(r"(?m)^on:\s*$", source):
        findings.append(f"{name}: missing explicit on: declaration")
    if not re.search(r"(?m)^ {2}workflow_dispatch:\s*(?:#.*)?$", source):
        findings.append(f"{name}: manual source qualification trigger is missing")
    if re.search(r"(?m)^ {4}inputs\s*:", source):
        findings.append(f"{name}: manual candidate inputs are forbidden")
    if re.search(r"\$\{\{\s*(?:inputs\b|github\.event\.inputs\b)", source):
        findings.append(f"{name}: caller-controlled GitHub expressions are forbidden")
    if "candidate_sha" in source.lower():
        findings.append(f"{name}: candidate_sha cannot select executable source")
    if not re.search(r"(?m)^ {4}if:\s*" + re.escape(MAIN_GUARD) + r"\s*$", source):
        findings.append(f"{name}: job must be restricted to the repository default main branch")
    if not re.search(r"(?m)^permissions:\s*\n {2}contents: read\s*$", source):
        findings.append(f"{name}: only read-only repository permission is permitted")
    if not re.search(r"(?m)^ {2}group:\s*[^\n]*" + re.escape(PLATFORM_SHA) + r"\s*$", source):
        findings.append(f"{name}: concurrency must use the platform-owned commit identity")
    if not re.search(r"(?m)^ {10}CANDIDATE_SHA:\s*" + re.escape(PLATFORM_SHA) + r"\s*$", source):
        findings.append(f"{name}: source verification must use the platform-owned commit SHA")

    checkouts = [step for step in STEP_SPLIT_RE.split(source) if CHECKOUT_RE.search(step)]
    if len(checkouts) != 1:
        findings.append(f"{name}: expected exactly one audited actions/checkout step")
    for step in checkouts:
        refs = re.findall(r"(?m)^ {10}ref:\s*(.*?)\s*$", step)
        if refs != [PLATFORM_SHA]:
            findings.append(f"{name}: checkout ref must be exactly the platform-owned github.sha")
        if not re.search(r"(?m)^ {10}persist-credentials: false\s*$", step):
            findings.append(f"{name}: checkout must not persist credentials")
    return findings


def main() -> int:
    findings: list[str] = []
    for name in PROTECTED_WORKFLOWS:
        path = WORKFLOW_DIR / name
        if path.is_symlink():
            findings.append(f"{name}: symlinked workflows are not trusted")
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(f"{name}: cannot read trusted source: {type(exc).__name__}")
            continue
        findings.extend(violations_from_text(name, source))

    if findings:
        print("Source qualification dispatch trust violations:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"Source dispatch trust passed for {len(PROTECTED_WORKFLOWS)} workflows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
