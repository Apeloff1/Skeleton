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
# A checkout can be written as either "- uses:" or "uses:" beneath "- id:".
# Split on every step, not just named steps, so extra checkouts cannot hide.
CHECKOUT_RE = re.compile(
    r"""(?m)^ {6}- uses:\s*['"]?actions/checkout@|^ {8}uses:\s*['"]?actions/checkout@"""
)
USES_RE = re.compile(r"(?m)^ {6}- uses:\s*(.*?)\s*$|^ {8}uses:\s*(.*?)\s*$")
STEP_SPLIT_RE = re.compile(r"(?m)(?=^ {6}- )")
PLATFORM_SHA = "${{ github.sha }}"
MAIN_GUARD = "github.repository == 'Apeloff1/Skeleton' && github.ref == 'refs/heads/main'"


def _top_level_section(source: str, key: str) -> str:
    """Return a top-level YAML block, ignoring unindented comments."""
    match = re.search(
        rf"(?ms)^{re.escape(key)}:\s*\n(.*?)(?=^[A-Za-z_-][A-Za-z_0-9-]*:|\Z)",
        source,
    )
    return match.group(1) if match else ""


def violations_from_text(name: str, source: str) -> list[str]:
    """Require trusted exact-main identity from dispatch to execution."""
    findings: list[str] = []
    # YAML duplicate keys can override a previously audited trusted value.
    for key in ("on", "permissions", "concurrency", "jobs"):
        if len(re.findall(rf"(?m)^{key}:", source)) != 1:
            findings.append(f"{name}: expected exactly one top-level {key} declaration")
    triggers = re.findall(r"(?m)^ {2}([A-Za-z_-]+):\s*(?:#.*)?$", _top_level_section(source, "on"))
    if triggers != ["workflow_dispatch"]:
        findings.append(f"{name}: only workflow_dispatch is permitted")
    permission_lines = [
        line.strip() for line in _top_level_section(source, "permissions").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if permission_lines != ["contents: read"]:
        findings.append(f"{name}: no token permissions beyond contents: read")
    job_names = re.findall(
        r"(?m)^ {2}([A-Za-z_][A-Za-z_0-9-]*):\s*(?:#.*)?$",
        _top_level_section(source, "jobs"),
    )
    if job_names != ["offline-source"]:
        findings.append(f"{name}: exactly one guarded offline-source job is required")
    if not re.search(r"(?m)^on:\s*$", source):
        findings.append(f"{name}: missing explicit on: declaration")
    if not re.search(r"(?m)^ {2}workflow_dispatch:\s*(?:#.*)?$", source):
        findings.append(f"{name}: manual source qualification trigger is missing")
    if re.search(r"(?m)^ {4}inputs\s*:", source):
        findings.append(f"{name}: manual candidate inputs are forbidden")
    if re.search(r"\$\{\{\s*(?:inputs\b|github\.event\.inputs\b)", source):
        findings.append(f"{name}: caller-controlled GitHub expressions are forbidden")
    # A trusted shell variable named CANDIDATE_SHA is allowed; only dispatch
    # input declarations and untrusted GitHub expressions are forbidden.
    guards = re.findall(r"(?m)^ {4}if:\s*(.*?)\s*$", _top_level_section(source, "jobs"))
    if guards != [MAIN_GUARD]:
        findings.append(f"{name}: job must be restricted to the repository default main branch")
    if not re.search(r"(?m)^permissions:\s*\n {2}contents: read\s*$", source):
        findings.append(f"{name}: only read-only repository permission is permitted")
    if not re.search(r"(?m)^ {2}group:\s*[^\n]*" + re.escape(PLATFORM_SHA) + r"\s*$", source):
        findings.append(f"{name}: concurrency must use the platform-owned commit identity")
    sha_values = re.findall(r"(?m)^ {10}CANDIDATE_SHA:\s*(.*?)\s*$", source)
    if not sha_values or any(value != PLATFORM_SHA for value in sha_values):
        findings.append(f"{name}: source verification must use the platform-owned commit SHA")
    if 'test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"' not in source:
        findings.append(f"{name}: missing exact checkout identity verification")

    # YAML aliases/expressions can conceal a checkout from a literal scanner.
    for inline, named in USES_RE.findall(source):
        value = (inline or named).strip()
        if value.startswith(("*", "&", "${{")):
            findings.append(f"{name}: dynamic or aliased action references are forbidden")
    steps = STEP_SPLIT_RE.split(source)
    checkouts = [step for step in steps if CHECKOUT_RE.search(step)]
    checkout_count = sum(len(CHECKOUT_RE.findall(step)) for step in steps)
    if checkout_count != 1 or len(checkouts) != 1:
        findings.append(f"{name}: expected exactly one audited actions/checkout step")
    for step in checkouts:
        refs = re.findall(r"(?m)^ {10}ref:\s*(.*?)\s*$", step)
        if refs != [PLATFORM_SHA]:
            findings.append(f"{name}: checkout ref must be exactly the platform-owned github.sha")
        if not re.search(r"(?m)^ {10}persist-credentials: false\s*$", step):
            findings.append(f"{name}: checkout must not persist credentials")
        if re.search(r"(?m)^ {10}(?:repository|path|submodules|ssh-key|token):", step):
            findings.append(f"{name}: checkout may not change repository, path or credential custody")
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
