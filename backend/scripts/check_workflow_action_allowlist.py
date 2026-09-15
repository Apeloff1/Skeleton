"""Reject unreviewed remote GitHub Actions and reusable workflows.

SHA pinning prevents a reviewed action revision from moving, but it does not stop a
new workflow from introducing an arbitrary action publisher.  This gate keeps
GitHub-owned actions broadly available while requiring every non-GitHub action
repository to be explicitly reviewed and listed here.
"""
from __future__ import annotations

from pathlib import Path
import sys

if __package__:
    from .check_workflow_security import (
        FLOW_USES_ENTRY_RE,
        USES_RE,
        _flow_mapping_entries,
        _flow_style_steps,
    )
else:
    from check_workflow_security import (
        FLOW_USES_ENTRY_RE,
        USES_RE,
        _flow_mapping_entries,
        _flow_style_steps,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# GitHub-maintained publishers are trusted at the owner boundary. Non-GitHub
# publishers must be reviewed repository-by-repository so approving one scanner
# or build helper cannot silently authorize every action from that publisher.
TRUSTED_ACTION_OWNERS = frozenset({"actions", "github"})
APPROVED_THIRD_PARTY_ACTIONS = frozenset(
    {
        "anchore/sbom-action",
        "aquasecurity/trivy-action",
        "docker/build-push-action",
        "docker/setup-buildx-action",
        "gacts/gitleaks",
    }
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _action_repository(reference: str) -> str | None:
    reference = reference.strip().strip("\"'")
    if reference.startswith("./") or reference.startswith("docker://"):
        return None

    target = reference.split("@", 1)[0]
    parts = target.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"{parts[0]}/{parts[1]}".lower()


def _reference_violation(path_name: str, number: int, reference: str) -> str | None:
    repository = _action_repository(reference)
    if repository is None:
        return None
    if not repository:
        return (
            f"{path_name}:{number}: remote action/reusable workflow has an invalid "
            f"repository reference: {reference}"
        )

    owner = repository.split("/", 1)[0]
    if owner in TRUSTED_ACTION_OWNERS or repository in APPROVED_THIRD_PARTY_ACTIONS:
        return None
    return (
        f"{path_name}:{number}: third-party action repository is not allowlisted: "
        f"{repository}; review it and add the exact owner/repository to "
        "APPROVED_THIRD_PARTY_ACTIONS before use"
    )


def violations(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    findings: list[str] = []
    flow_style_lines: set[int] = set()

    for number, fragment in _flow_style_steps(lines):
        fragment_lines = fragment.splitlines()
        flow_style_lines.update(range(number, number + len(fragment_lines)))
        for entry in _flow_mapping_entries(fragment):
            match = FLOW_USES_ENTRY_RE.match(entry.strip())
            if not match:
                continue
            reference = match.group(1).strip("\"'")
            finding = _reference_violation(path.name, number, reference)
            if finding:
                findings.append(finding)

    for index, line in enumerate(lines):
        number = index + 1
        if number in flow_style_lines:
            continue
        match = USES_RE.match(line)
        if not match:
            continue
        reference = match.group(1).strip("\"'")
        finding = _reference_violation(path.name, number, reference)
        if finding:
            findings.append(finding)

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
        print("GitHub Actions allowlist violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Workflow action allowlist passed for {len(workflows)} workflow files; "
        f"approved third-party repositories: {len(APPROVED_THIRD_PARTY_ACTIONS)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
