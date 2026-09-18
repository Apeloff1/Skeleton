"""Fail-closed contract: workflow_run consumers handle every completing branch."""
from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
ALL_BRANCH_GLOBS = 'branches:\n      - "*"\n      - "**"'
WORKFLOW_RUN_TRIGGER_RE = re.compile(r"(?m)^  workflow_run:\s*(?:#.*)?$")
HINT_ARRAY_EXPR = "toJSON(github.event.workflow_run.pull_requests.*.number)"
COMMIT_OID_PATTERN = r"^[0-9a-f]{40}$"
AUTOMATION_WORKFLOW = "pr-automation-index.yml"
AUTOMATION_MAIN_ONLY_EXCLUSION_RE = re.compile(
    r'(?m)^    branches-ignore:\s*\n(?P<items>(?:      - .+\n)+)'
)
DRAIN_WORKFLOW = "pr-obsolete-run-drain.yml"
REPAIR_WORKFLOW = "repair-intake.yml"
IDLE_WORKFLOW = "idle-studio.yml"
MISSING_IDENTITY = "workflow_run completion is missing head SHA or branch"
OID_IDENTITY = "workflow_run head SHA must be a 40-character hex commit OID"
IDENTITY_ADAPTERS = (
    REPO_ROOT / "backend/scripts/pr_obsolete_run_drain.py",
    REPO_ROOT / "skeleton/pr_automation/runner.py",
    REPO_ROOT / "skeleton/automation/repair_intake.py",
    REPO_ROOT / "skeleton/automation/idle_studio.py",
)
IDENTITY_CALLERS = (
    REPO_ROOT / "backend/scripts/pr_obsolete_run_from_workflow_run.py",
    REPO_ROOT / "backend/scripts/pr_obsolete_run_sweep.py",
)


def workflow_files(directory: Path = WORKFLOW_DIR) -> list[Path]:
    return sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])


def _is_named(path_name: str, expected: str) -> bool:
    return path_name == expected or path_name.endswith(expected)


def violations_for_text(path_name: str, text: str) -> list[str]:
    findings: list[str] = []
    if WORKFLOW_RUN_TRIGGER_RE.search(text) is None:
        return findings

    has_all_branch_globs = ALL_BRANCH_GLOBS in text
    automation_main_only_exclusion = False
    if _is_named(path_name, AUTOMATION_WORKFLOW):
        match = AUTOMATION_MAIN_ONLY_EXCLUSION_RE.search(text)
        if match is not None:
            ignored = [
                line.removeprefix("      - ").strip().strip("'\\\"")
                for line in match.group("items").splitlines()
                if line.strip()
            ]
            automation_main_only_exclusion = ignored == ["main"]

    if not has_all_branch_globs and not automation_main_only_exclusion:
        findings.append(
            f"{path_name}: workflow_run consumers must match every completing head "
            'with branches: ["*", "**"]; PR Automation may exclude only main '
            "because scheduled reconciliation covers the default branch"
        )
    if "pull_requests[0]" in text:
        findings.append(
            f"{path_name}: pull_requests[0] is not a complete branch-completion identity"
        )
    if "github.event.workflow_run.pull_requests" in text and HINT_ARRAY_EXPR not in text:
        findings.append(
            f"{path_name}: branch completions must consume the complete pull_requests hint array"
        )

    if _is_named(path_name, AUTOMATION_WORKFLOW):
        if "github.event.workflow_run.head_sha" not in text:
            findings.append(f"{path_name}: branch completions must use workflow_run.head_sha")
        if "github.event.workflow_run.head_branch" not in text:
            findings.append(f"{path_name}: branch completions must use workflow_run.head_branch")
        if HINT_ARRAY_EXPR not in text:
            findings.append(
                f"{path_name}: branch completions must consume the complete pull_requests hint array"
            )
        if "--pr-hints-json" not in text:
            findings.append(f"{path_name}: branch completions must pass JSON PR hints to trusted Python")
        if "--head-sha" not in text or "--head-ref" not in text:
            findings.append(f"{path_name}: branch completions must pass head SHA and branch identity")
        if 'pr="${INPUT_PR:-${WORKFLOW_RUN_PR:-}}"' in text:
            findings.append(
                f"{path_name}: workflow_run completions must not treat a single PR hint as identity"
            )

    if _is_named(path_name, DRAIN_WORKFLOW):
        if "github.event.workflow_run.head_sha" not in text:
            findings.append(f"{path_name}: branch completions must use workflow_run.head_sha")
        if "github.event.workflow_run.head_branch" not in text:
            findings.append(f"{path_name}: branch completions must use workflow_run.head_branch")
        if HINT_ARRAY_EXPR not in text:
            findings.append(
                f"{path_name}: branch completions must consume the complete pull_requests hint array"
            )
        if "WORKFLOW_RUN_PR_HINTS" not in text:
            findings.append(
                f"{path_name}: branch completions must pass JSON PR hints to trusted Python"
            )

    if _is_named(path_name, REPAIR_WORKFLOW):
        if "github.event.workflow_run.head_sha" not in text:
            findings.append(f"{path_name}: branch completions must use workflow_run.head_sha")
        if "github.event.workflow_run.head_branch" not in text:
            findings.append(f"{path_name}: branch completions must use workflow_run.head_branch")
        if HINT_ARRAY_EXPR not in text:
            findings.append(
                f"{path_name}: branch completions must consume the complete pull_requests hint array"
            )
        if "WORKFLOW_RUN_PR_HINTS" not in text:
            findings.append(
                f"{path_name}: branch completions must pass JSON PR hints to trusted Python"
            )
        if MISSING_IDENTITY not in text:
            findings.append(
                f"{path_name}: branch completions must fail closed without head SHA and branch"
            )
        if COMMIT_OID_PATTERN not in text or OID_IDENTITY not in text:
            findings.append(
                f"{path_name}: branch completions must canonicalize head SHA as a 40-hex commit OID"
            )

    if _is_named(path_name, IDLE_WORKFLOW):
        same_repo_guard = (
            "github.event.workflow_run.head_repository.full_name == github.repository"
        )
        # Both pressure and studio are workflow_run consumers. Requiring the
        # guard only once lets one job silently lose the trust boundary while
        # another occurrence masks the regression.
        if text.count(same_repo_guard) < 2:
            findings.append(
                f"{path_name}: branch completions must reject cross-repository workflow_run heads"
            )
        if "exceeded bounded identity scan" not in text:
            findings.append(
                f"{path_name}: branch completions must fail closed on truncated live snapshots"
            )
        if 'gh api "/repos/$REPO/actions/runs?per_page=50"' in text:
            findings.append(
                f"{path_name}: live workflow_run snapshots must paginate Actions runs"
            )
        if COMMIT_OID_PATTERN not in text:
            findings.append(
                f"{path_name}: live snapshots must canonicalize the trusted base SHA as a 40-hex commit OID"
            )
    return findings


def _adapter_oid_violations() -> list[str]:
    findings: list[str] = []
    for path in IDENTITY_ADAPTERS:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(f"{path}: unable to read identity adapter: {exc}")
            continue
        if COMMIT_OID_PATTERN not in text or "canonical_commit_oid" not in text:
            findings.append(
                f"{path.name}: branch completions must canonicalize head SHA as a 40-hex commit OID"
            )
        if path.name == "pr_obsolete_run_drain.py" and "cache[sha] = False" in text:
            findings.append(
                f"{path.name}: commit PR association HTTP errors must fail closed"
            )
        if path.name == "runner.py" and "statuses/{quoted_sha}" not in text:
            findings.append(
                f"{path.name}: gate status publish must quote a canonical commit OID"
            )
    for path in IDENTITY_CALLERS:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(f"{path}: unable to read identity adapter: {exc}")
            continue
        if "canonical_commit_oid" not in text:
            findings.append(
                f"{path.name}: branch completions must canonicalize head SHA as a 40-hex commit OID"
            )
    return findings


def violations(directory: Path = WORKFLOW_DIR) -> list[str]:
    findings: list[str] = []
    try:
        files = workflow_files(directory)
    except OSError as exc:
        return [f"{directory}: unable to enumerate workflows: {exc}"]
    if not files:
        return [f"{directory}: no GitHub Actions workflows found"]
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(f"{path}: unable to read workflow: {exc}")
            continue
        findings.extend(violations_for_text(path.name, text))
    findings.extend(_adapter_oid_violations())
    return findings


def main() -> int:
    findings = violations()
    if findings:
        print("Workflow-run branch-completion contract violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Workflow-run branch-completion contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
