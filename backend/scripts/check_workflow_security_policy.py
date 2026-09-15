"""Hardened workflow security policy with a narrow pull_request_target exception."""
from __future__ import annotations

from pathlib import Path
import re
import sys

if __package__:
    from .check_workflow_security import violations as base_violations
else:
    from check_workflow_security import violations as base_violations

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
PR_TARGET_ALLOWLIST = {"pr-hygiene.yml"}
PR_TARGET_RE = re.compile(r"^\s*(?:pull_request_target|'pull_request_target'|\"pull_request_target\")\s*:", re.M)
USES_RE = re.compile(r"^\s*(?:-\s*)?(?:uses|'uses'|\"uses\")\s*:", re.M)
PR_EVENT_EXPR_RE = re.compile(
    r"\$\{\{\s*github\.event\.pull_request\.(?P<field>[A-Za-z0-9_.-]+)",
    re.I,
)
WRITE_SCOPE_RE = re.compile(
    r"^\s+[\"']?(?P<scope>[A-Za-z0-9_-]+)[\"']?\s*:\s*write\s*(?:#.*)?$",
    re.I | re.M,
)
WRITE_ALL_RE = re.compile(r"^\s*permissions\s*:\s*write-all\s*(?:#.*)?$", re.I | re.M)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _is_pull_request_target(text: str) -> bool:
    return bool(PR_TARGET_RE.search(text))


def _privileged_trigger_findings(path: Path, text: str) -> list[str]:
    if not _is_pull_request_target(text):
        return []
    if path.name not in PR_TARGET_ALLOWLIST:
        return []  # base policy keeps the categorical rejection for every other workflow.

    findings: list[str] = []

    if USES_RE.search(text):
        findings.append(
            f"{path.name}: allowlisted pull_request_target workflow must not use actions or reusable workflows; "
            "keep it metadata-only and shell-local"
        )

    if WRITE_ALL_RE.search(text):
        findings.append(f"{path.name}: write-all permissions are forbidden in privileged workflow")

    for match in WRITE_SCOPE_RE.finditer(text):
        scope = match.group("scope").lower()
        if scope != "issues":
            findings.append(
                f"{path.name}: privileged workflow may only elevate issues: write; found {scope}: write"
            )

    for match in PR_EVENT_EXPR_RE.finditer(text):
        field = match.group("field").lower()
        if field != "number":
            findings.append(
                f"{path.name}: privileged workflow may only interpolate github.event.pull_request.number; "
                f"found pull request field {field}"
            )

    return findings


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    findings = base_violations(path)
    if _is_pull_request_target(text) and path.name in PR_TARGET_ALLOWLIST:
        findings = [
            finding
            for finding in findings
            if "pull_request_target is forbidden" not in finding
        ]
        findings.extend(_privileged_trigger_findings(path, text))
    return findings


def main() -> int:
    workflows = workflow_files()
    if not workflows:
        print("No GitHub Actions workflows found.", file=sys.stderr)
        return 1

    findings: list[str] = []
    for path in workflows:
        findings.extend(violations(path))

    if findings:
        print("GitHub Actions workflow security violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(f"Workflow security policy passed for {len(workflows)} workflow files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
