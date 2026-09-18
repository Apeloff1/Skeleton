"""Fail-closed contract gate for the Repository Attention workflow."""
from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "repo-attention.yml"

REQUIRED_PR_TYPES = {
    "synchronize",
    "edited",
    "reopened",
    "closed",
    "ready_for_review",
    "converted_to_draft",
    "assigned",
    "unassigned",
    "milestoned",
    "demilestoned",
    "review_requested",
    "review_request_removed",
    "locked",
    "unlocked",
    "auto_merge_enabled",
    "auto_merge_disabled",
    "enqueued",
    "dequeued",
}
REQUIRED_ISSUE_TYPES = {
    "edited",
    "reopened",
    "closed",
    "assigned",
    "unassigned",
    "milestoned",
    "demilestoned",
    "locked",
    "unlocked",
}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
WRITE_SCOPE_RE = re.compile(r"^\s+([A-Za-z0-9_-]+):\s*write\s*(?:#.*)?$", re.MULTILINE)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _block(text: str, key: str, indent: int) -> str:
    lines = text.splitlines()
    prefix = " " * indent + key + ":"
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        suffix = line[len(prefix) :]
        if suffix and not suffix.lstrip().startswith("#"):
            # The key can have an inline value; retain it in the returned block.
            pass
        collected = [line]
        for child in lines[index + 1 :]:
            stripped = child.strip()
            if stripped and not stripped.startswith("#") and _indent(child) <= indent:
                break
            collected.append(child)
        return "\n".join(collected)
    return ""


def _has_token(block: str, token: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])", block) is not None


def violations_for_text(text: str) -> list[str]:
    findings: list[str] = []

    if re.search(r"(?m)^\s*pull_request_target\s*:", text):
        findings.append("pull_request_target is forbidden by the repository workflow-security policy")
    if not re.search(r"(?m)^\s{2}pull_request\s*:", text):
        findings.append("ordinary pull_request trigger is required")
    if not re.search(r"(?m)^permissions:\s*\{\}\s*(?:#.*)?$", text):
        findings.append("workflow scope must fail closed with permissions: {}")
    if re.search(r"(?m)^\s*-?\s*uses\s*:", text):
        findings.append("repository-attention must remain metadata/API-only and must not use actions or checkout")
    if "|| true" in text:
        findings.append("blanket || true error suppression is forbidden in repository-attention")

    for scope in WRITE_SCOPE_RE.findall(text):
        if scope != "issues":
            findings.append(f"unexpected write permission scope: {scope}: write")

    concurrency = _block(text, "concurrency", 0)
    if "github.event.issue.number || github.event.pull_request.number || 'sweep'" not in concurrency:
        findings.append("concurrency must serialize all event families by issue/PR number")
    if not re.search(r"(?m)^\s{2}cancel-in-progress:\s*false\s*$", concurrency):
        findings.append("repository-attention must not cancel in-flight trusted clears")

    issue_trigger = _block(text, "issues", 2)
    for event in sorted(REQUIRED_ISSUE_TYPES):
        if not _has_token(issue_trigger, event):
            findings.append(f"issues trigger is missing activity type: {event}")

    comment_trigger = _block(text, "issue_comment", 2)
    for event in ("created", "edited"):
        if not _has_token(comment_trigger, event):
            findings.append(f"issue_comment trigger is missing activity type: {event}")

    pr_trigger = _block(text, "pull_request", 2)
    for event in sorted(REQUIRED_PR_TYPES):
        if not _has_token(pr_trigger, event):
            findings.append(f"pull_request trigger is missing activity type: {event}")

    review_trigger = _block(text, "pull_request_review", 2)
    for event in ("submitted", "edited"):
        if not _has_token(review_trigger, event):
            findings.append(f"pull_request_review trigger is missing activity type: {event}")

    review_comment_trigger = _block(text, "pull_request_review_comment", 2)
    for event in ("created", "edited"):
        if not _has_token(review_comment_trigger, event):
            findings.append(f"pull_request_review_comment trigger is missing activity type: {event}")

    clear_pr = _block(text, "clear-pr-attention", 2)
    if "github.event.pull_request.head.repo.full_name == github.repository" not in clear_pr:
        findings.append("PR label mutation must be restricted to same-repository heads")
    if "issues: write" not in clear_pr:
        findings.append("PR clear job needs only issues: write for label mutation")

    clear_comment = _block(text, "clear-comment-attention", 2)
    if "github.event.sender.type != 'Bot'" not in clear_comment:
        findings.append("comment-driven clearing must reject bots")
    for association in TRUSTED_ASSOCIATIONS:
        if f"author_association == '{association}'" not in clear_comment:
            findings.append(f"comment-driven clearing must retain trusted association: {association}")
    if "github.event.issue.pull_request != null" not in clear_comment:
        findings.append("stale-draft comment clearing must be conditioned on an actual pull request")

    clear_review = _block(text, "clear-review-attention", 2)
    if "github.event.pull_request.head.repo.full_name == github.repository" not in clear_review:
        findings.append("review label mutation must be restricted to same-repository heads")
    if "github.event.sender.type != 'Bot'" not in clear_review:
        findings.append("review-driven clearing must reject bots")
    for association in TRUSTED_ASSOCIATIONS:
        if clear_review.count(f"author_association == '{association}'") < 2:
            findings.append(
                f"review and review-comment clearing must both retain trusted association: {association}"
            )

    sweep = _block(text, "sweep", 2)
    required_sweep_markers = {
        "timeline activity clock": "/timeline?per_page=100",
        "meaningful activity helper": "last_meaningful_activity",
        "managed label exclusion": '$kind == "labeled"',
        "managed unlabel exclusion": '$kind == "unlabeled"',
        "bot exclusion": '!= "Bot"',
        "commit timestamp extraction": "$e.committer.date // $e.author.date",
        "closed-item repair": "state=closed&labels=${label}",
    }
    for label, marker in required_sweep_markers.items():
        if marker not in sweep:
            findings.append(f"sweep contract missing {label}")
    # Both the PR reconciler and issue reconciler must run a second snapshot
    # pass. Checking only for one generic loop lets one path silently regress.
    if sweep.count("for pass in 1 2; do") < 2:
        findings.append("sweep contract missing two-pass convergence")
    if "[.number, .updated_at" in sweep or "updated_epoch=$(date" in sweep:
        findings.append("generic updated_at must not be used as the inactivity clock")
    if "Failed to remove ${label}" not in sweep:
        findings.append("sweep label deletion must fail on persistent API failures")

    return findings


def violations(path: Path = WORKFLOW) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: unable to read repository-attention workflow: {exc}"]
    return violations_for_text(text)


def main() -> int:
    findings = violations()
    if findings:
        print("Repository Attention contract violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Repository Attention contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
