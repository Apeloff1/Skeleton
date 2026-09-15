"""Fail-closed safety contract for the branch-flow maintenance workflow."""
from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-flow.yml"

REQUIRED_ACTIVE_STATUSES = {"requested", "waiting", "pending", "queued", "in_progress"}
WRITE_SCOPE_RE = re.compile(r"^\s+([A-Za-z0-9_-]+):\s*write\s*(?:#.*)?$", re.MULTILINE)
WORKFLOW_SCAN_RE = re.compile(
    r"def touches_workflows\(number, expected_files\):(?P<body>.*?)(?=\n\s+def live_validation\()",
    re.DOTALL,
)


def violations_for_text(text: str) -> list[str]:
    findings: list[str] = []

    if re.search(r"(?m)^\s{2}pull_request(?:_target)?\s*:", text):
        findings.append("write-capable branch-flow must never run on pull-request events")
    if not re.search(r"(?m)^permissions:\s*\{\}\s*(?:#.*)?$", text):
        findings.append("branch-flow must fail closed at workflow scope with permissions: {}")
    if not re.search(r"(?m)^\s{2}cancel-in-progress:\s*false\s*$", text):
        findings.append("branch-flow must not cancel an in-flight mutation pass")
    if "github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'" not in text:
        findings.append("manual branch-flow execution must be restricted to main")
    if re.search(r"(?m)^\s*-\s*uses\s*:", text):
        findings.append("branch-flow must remain checkout/action-free")

    write_scopes = WRITE_SCOPE_RE.findall(text)
    if write_scopes != ["contents"]:
        findings.append("branch-flow must have exactly one write scope: contents: write")
    for marker in ("actions: read", "contents: write", "pull-requests: read"):
        if marker not in text:
            findings.append(f"branch-flow permission contract missing {marker}")

    if "/update-branch" in text:
        findings.append("asynchronous update-branch endpoint is forbidden")
    if "f'/repos/{repo}/merges'" not in text:
        findings.append("synchronous repository merge endpoint is required")
    if "expected_head_sha" in text:
        findings.append("legacy asynchronous update-branch acceptance guard must not return")

    for status in REQUIRED_ACTIVE_STATUSES:
        if f"'{status}'" not in text:
            findings.append(f"active CI detection missing status: {status}")
    if "min_head_age_seconds = 180" not in text:
        findings.append("branch-flow must retain the 180-second head settle window")
    if "fresh_head.get('sha') != expected_head" not in text:
        findings.append("branch-flow must revalidate the head SHA immediately before mutation")
    if "head_repo != repo" not in text:
        findings.append("branch-flow must preserve fork PR branches")
    if "pr.get('draft')" not in text:
        findings.append("branch-flow must preserve draft PR branches")

    if "def touches_workflows(number, expected_files):" not in text:
        findings.append("branch-flow must inspect the complete changed-file set for workflow changes")
    if "startswith('.github/workflows/')" not in text:
        findings.append("branch-flow must preserve PRs that modify workflow files")
    if "('filename', 'previous_filename')" not in text:
        findings.append("branch-flow must detect workflow files on both sides of a rename")
    if "seen >= expected_files" not in text or "for page in range(1, 31):" not in text:
        findings.append("workflow-file enumeration must prove completeness or fail closed")
    workflow_scan = WORKFLOW_SCAN_RE.search(text)
    if not workflow_scan or not workflow_scan.group("body").rstrip().endswith("return None"):
        findings.append("bounded workflow-file enumeration must fail closed when the scan limit is exhausted")
    if "workflow_change = touches_workflows(number, pr.get('changed_files'))" not in text:
        findings.append("initial workflow-file exclusion must use the PR changed-file count")
    if "if touches_workflows(number, fresh.get('changed_files')) is not False:" not in text:
        findings.append("workflow-file exclusion must be revalidated immediately before mutation")

    if "permission_or_api_failure" not in text or "raise SystemExit" not in text:
        findings.append("terminal branch-flow API/permission failures must fail the run")
    if "max_updates = 4" not in text:
        findings.append("branch-flow must retain a bounded per-pass mutation cap")

    return findings


def violations(path: Path = WORKFLOW) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: unable to read branch-flow workflow: {exc}"]
    return violations_for_text(text)


def main() -> int:
    findings = violations()
    if findings:
        print("Branch-flow contract violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Branch-flow contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
