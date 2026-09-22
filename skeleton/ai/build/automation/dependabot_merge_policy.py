"""Fail-closed Dependabot merge policy for trusted default-branch automation.

The worker never executes pull-request code. It validates immutable PR identity,
a narrow dependency-file allowlist, exact-head successful workflow evidence, and
that the candidate contains the current default-branch head before attempting a
SHA-bound squash merge.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
import subprocess
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote


DEFAULT_REQUIRED_WORKFLOWS = (
    "CI/CD",
    "Merge Readiness",
    "Secret scanning",
    "Malware Gate",
    "Repository Hygiene Gate",
    "Artifact Policy",
    "Provenance Policy",
    "PR Hygiene",
    "Dependency Review",
)

_ALLOWED_FILENAMES = {
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
}

_BACKEND_QUALITY_PREFIXES = (
    ".emergent/cron/",
    "backend/",
    "skeleton/",
    "frontend/",
)

_DEFAULT_MAX_MERGES = 3
_MAX_MERGES_HARD_LIMIT = 10


@dataclass(frozen=True, slots=True)
class MergeDecision:
    ready: bool
    reasons: tuple[str, ...]
    head_sha: str = ""


def _canonical_path(path: str) -> str | None:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        return None
    pure = PurePosixPath(path)
    normalized = pure.as_posix()
    if (
        pure.is_absolute()
        or normalized != path
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        return None
    return normalized


def _snapshot_path(path: str) -> bool:
    return path.startswith("satellites/") and "/branch-snapshots/" in path


def dependency_path_allowed(path: str) -> bool:
    """Allow only canonical live dependency manifests/lockfiles.

    Archived branch snapshots are evidence, not an executable dependency
    surface, even when a historical filename happens to match the allowlist.
    """
    normalized = _canonical_path(path)
    if normalized is None or _snapshot_path(normalized):
        return False
    name = PurePosixPath(normalized).name.lower()
    if name in _ALLOWED_FILENAMES:
        return True
    return name.startswith("requirements") and name.endswith(".txt")


def dependency_review_applicable(files: Sequence[str]) -> bool:
    """Every auto-mergeable dependency file must be covered by Dependency Review."""
    return any(dependency_path_allowed(path) for path in files)


def dependency_surface_guard_applicable(files: Sequence[str]) -> bool:
    """Mirror the current Dependency Surface Guard trigger relevant to auto-merge."""
    return any(_canonical_path(path) == "pyproject.toml" for path in files)


def backend_quality_applicable(files: Sequence[str]) -> bool:
    """Mirror Backend Quality's broad code-root path filters."""
    for raw_path in files:
        path = _canonical_path(raw_path)
        if path is not None and path.startswith(_BACKEND_QUALITY_PREFIXES):
            return True
    return False


def required_workflows_for_files(
    files: Sequence[str],
    *,
    base_required: Sequence[str] = DEFAULT_REQUIRED_WORKFLOWS,
) -> tuple[str, ...]:
    required = [
        name.strip()
        for name in base_required
        if isinstance(name, str) and name.strip()
    ]
    extras: list[str] = []
    if dependency_review_applicable(files):
        extras.append("Dependency Review")
    if dependency_surface_guard_applicable(files):
        extras.append("Dependency Surface Guard")
    if backend_quality_applicable(files):
        extras.append("Backend Quality")
    return tuple(dict.fromkeys([*required, *extras]))


def _latest_runs_by_name(
    runs: Iterable[Mapping[str, Any]], head_sha: str
) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for run in runs:
        if run.get("head_sha") != head_sha or run.get("event") != "pull_request":
            continue
        name = run.get("name")
        if not isinstance(name, str) or not name:
            continue
        current = latest.get(name)
        key = (int(run.get("run_number") or 0), int(run.get("run_attempt") or 0))
        current_key = (
            (
                int(current.get("run_number") or 0),
                int(current.get("run_attempt") or 0),
            )
            if current is not None
            else (-1, -1)
        )
        if key >= current_key:
            latest[name] = run
    return latest


def _identity_reasons(pr: Mapping[str, Any], *, base_branch: str) -> list[str]:
    reasons: list[str] = []
    author = pr.get("author")
    login = author.get("login") if isinstance(author, Mapping) else None
    if login != "dependabot[bot]":
        reasons.append("untrusted_author")
    head_ref = pr.get("headRefName")
    if not isinstance(head_ref, str) or not head_ref.startswith("dependabot/"):
        reasons.append("untrusted_head")
    if pr.get("isCrossRepository") is not False:
        reasons.append("cross_repository_head")
    if pr.get("baseRefName") != base_branch:
        reasons.append("wrong_base")
    if pr.get("state") != "OPEN" or pr.get("isDraft") is not False:
        reasons.append("not_open_ready_pr")
    if pr.get("mergeable") != "MERGEABLE":
        reasons.append("not_mergeable")
    if not str(pr.get("headRefOid") or ""):
        reasons.append("missing_head_sha")
    return reasons


def evaluate_candidate(
    pr: Mapping[str, Any],
    files: Sequence[str],
    runs: Iterable[Mapping[str, Any]],
    *,
    base_branch: str,
    required_workflows: Sequence[str] = DEFAULT_REQUIRED_WORKFLOWS,
) -> MergeDecision:
    reasons = _identity_reasons(pr, base_branch=base_branch)
    head_sha = str(pr.get("headRefOid") or "")

    if not files:
        reasons.append("empty_diff")
    elif any(not dependency_path_allowed(path) for path in files):
        reasons.append("out_of_scope_file")

    required = tuple(
        name.strip()
        for name in required_workflows
        if isinstance(name, str) and name.strip()
    )
    if not required:
        reasons.append("no_required_workflows")

    latest = _latest_runs_by_name(runs, head_sha)
    for workflow in required:
        run = latest.get(workflow)
        if run is None:
            reasons.append(f"missing_workflow:{workflow}")
            continue
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            reasons.append(f"workflow_not_green:{workflow}")

    return MergeDecision(not reasons, tuple(reasons), head_sha=head_sha)


def same_candidate_identity(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Require immutable merge-relevant PR identity across the mutation boundary."""
    fields = (
        "number",
        "headRefOid",
        "headRefName",
        "baseRefName",
        "state",
        "isDraft",
        "isCrossRepository",
    )
    if any(before.get(field) != after.get(field) for field in fields):
        return False
    before_author = before.get("author")
    after_author = after.get("author")
    before_login = before_author.get("login") if isinstance(before_author, Mapping) else None
    after_login = after_author.get("login") if isinstance(after_author, Mapping) else None
    return before_login == after_login == "dependabot[bot]"


def _looks_like_dependabot(pr: Mapping[str, Any], *, base_branch: str) -> bool:
    return not _identity_reasons(pr, base_branch=base_branch)


class GitHubCLI:
    def __init__(self, repo: str, *, timeout: int = 30) -> None:
        self.repo = repo
        self.timeout = timeout

    def _run(self, args: Sequence[str], *, timeout: int | None = None) -> str:
        completed = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout or self.timeout,
        )
        return completed.stdout

    def _json(self, args: Sequence[str]) -> Any:
        return json.loads(self._run(args) or "null")

    def open_prs(self) -> list[Mapping[str, Any]]:
        payload = self._json(
            [
                "pr",
                "list",
                "--repo",
                self.repo,
                "--state",
                "open",
                "--limit",
                "1000",
                "--json",
                "number,author,headRefName,headRefOid,baseRefName,isDraft,state,mergeable,isCrossRepository",
            ]
        )
        return payload if isinstance(payload, list) else []

    def pr(self, number: int) -> Mapping[str, Any]:
        payload = self._json(
            [
                "pr",
                "view",
                str(number),
                "--repo",
                self.repo,
                "--json",
                "number,author,headRefName,headRefOid,baseRefName,isDraft,state,mergeable,isCrossRepository",
            ]
        )
        return payload if isinstance(payload, Mapping) else {}

    def files(self, number: int) -> list[str]:
        payload = self._json(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{self.repo}/pulls/{number}/files?per_page=100",
            ]
        )
        pages = payload if isinstance(payload, list) else []
        result: list[str] = []
        for page in pages:
            if not isinstance(page, list):
                continue
            for item in page:
                if isinstance(item, Mapping) and isinstance(item.get("filename"), str):
                    result.append(item["filename"])
        return result

    def runs(self, head_sha: str) -> list[Mapping[str, Any]]:
        payload = self._json(
            [
                "api",
                "-X",
                "GET",
                "--paginate",
                "--slurp",
                f"repos/{self.repo}/actions/runs?head_sha={head_sha}&event=pull_request&per_page=100",
            ]
        )
        pages = payload if isinstance(payload, list) else []
        result: list[Mapping[str, Any]] = []
        for page in pages:
            if not isinstance(page, Mapping):
                continue
            workflow_runs = page.get("workflow_runs")
            if isinstance(workflow_runs, list):
                result.extend(run for run in workflow_runs if isinstance(run, Mapping))
        return result

    def branch_head(self, branch: str) -> str:
        payload = self._json(
            [
                "api",
                "-X",
                "GET",
                f"repos/{self.repo}/branches/{quote(branch, safe='')}",
            ]
        )
        commit = payload.get("commit") if isinstance(payload, Mapping) else None
        sha = commit.get("sha") if isinstance(commit, Mapping) else None
        if not isinstance(sha, str) or not sha:
            raise RuntimeError("default-branch head could not be resolved")
        return sha

    def head_contains_base(self, base_sha: str, head_sha: str) -> bool:
        if not base_sha or not head_sha:
            return False
        payload = self._json(
            [
                "api",
                "-X",
                "GET",
                f"repos/{self.repo}/compare/{base_sha}...{head_sha}",
            ]
        )
        return isinstance(payload, Mapping) and payload.get("behind_by") == 0

    def merge(self, number: int, expected_head_sha: str) -> None:
        payload = self._json(
            [
                "api",
                "-X",
                "PUT",
                f"repos/{self.repo}/pulls/{number}/merge",
                "-f",
                f"sha={expected_head_sha}",
                "-f",
                "merge_method=squash",
            ]
        )
        if not isinstance(payload, Mapping) or payload.get("merged") is not True:
            raise RuntimeError("Dependabot merge was not accepted")


def required_workflows_from_env(files: Sequence[str]) -> tuple[str, ...]:
    """Allow configuration to add gates, never to remove the safety baseline."""
    raw = os.getenv("DEPENDABOT_REQUIRED_WORKFLOWS", "")
    additions = tuple(
        dict.fromkeys(part.strip() for part in raw.split(",") if part.strip())
    )
    base = tuple(dict.fromkeys([*DEFAULT_REQUIRED_WORKFLOWS, *additions]))
    return required_workflows_for_files(files, base_required=base)


def max_merges_from_env() -> int:
    raw = os.getenv("DEPENDABOT_MAX_MERGES", str(_DEFAULT_MAX_MERGES)).strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_MERGES
    return max(1, min(value, _MAX_MERGES_HARD_LIMIT))


def run_once(repo: str, base_branch: str) -> int:
    client = GitHubCLI(repo)
    merged = 0
    merge_cap = max_merges_from_env()

    for summary in client.open_prs():
        if merged >= merge_cap:
            break
        number = summary.get("number")
        if not isinstance(number, int) or not _looks_like_dependabot(
            summary, base_branch=base_branch
        ):
            continue

        initial_base_head = client.branch_head(base_branch)
        files = client.files(number)
        required = required_workflows_from_env(files)
        runs = client.runs(str(summary.get("headRefOid") or ""))
        decision = evaluate_candidate(
            summary,
            files,
            runs,
            base_branch=base_branch,
            required_workflows=required,
        )
        if not decision.ready or not client.head_contains_base(
            initial_base_head, decision.head_sha
        ):
            continue

        # Re-read every merge-relevant input immediately before mutation.
        current = client.pr(number)
        current_base_head = client.branch_head(base_branch)
        if current_base_head != initial_base_head or not same_candidate_identity(
            summary, current
        ):
            continue

        current_files = client.files(number)
        current_required = required_workflows_from_env(current_files)
        current_runs = client.runs(str(current.get("headRefOid") or ""))
        final = evaluate_candidate(
            current,
            current_files,
            current_runs,
            base_branch=base_branch,
            required_workflows=current_required,
        )
        if (
            not final.ready
            or final.head_sha != decision.head_sha
            or current_files != files
            or current_required != required
            or not client.head_contains_base(current_base_head, final.head_sha)
        ):
            continue

        # GitHub's merge API can bind the head SHA but has no expected-base-SHA
        # parameter. Re-read the base at the final boundary and fail closed on
        # every observed move; branch protection remains defense in depth.
        if client.branch_head(base_branch) != current_base_head:
            continue
        client.merge(number, final.head_sha)
        merged += 1

    return merged


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Dependabot merge worker")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="main")
    args = parser.parse_args(argv)
    run_once(args.repo, args.base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
