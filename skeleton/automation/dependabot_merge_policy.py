"""Fail-closed Dependabot merge policy for trusted default-branch automation.

The policy never executes pull-request code. It validates immutable PR identity,
a narrow dependency-file allowlist, successful workflow runs for the exact head
SHA, and that the candidate head contains the current default-branch head before
allowing a merge attempt. The final merge API call is also bound to the exact
validated head SHA so a last-moment head move cannot be merged.
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
    "Backend Quality",
    "Merge Readiness",
    "Secret scanning",
    "Malware Gate",
    "Repository Hygiene Gate",
    "Artifact Policy",
    "Provenance Policy",
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
    if pure.is_absolute() or normalized != path or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    return normalized


def dependency_path_allowed(path: str) -> bool:
    normalized = _canonical_path(path)
    if normalized is None:
        return False
    name = PurePosixPath(normalized).name.lower()
    if name in _ALLOWED_FILENAMES:
        return True
    if name.startswith("requirements") and name.endswith(".txt"):
        return True
    return False


def _latest_runs_by_name(runs: Iterable[Mapping[str, Any]], head_sha: str) -> dict[str, Mapping[str, Any]]:
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
            int(current.get("run_number") or 0),
            int(current.get("run_attempt") or 0),
        ) if current is not None else (-1, -1)
        if key >= current_key:
            latest[name] = run
    return latest


def evaluate_candidate(
    pr: Mapping[str, Any],
    files: Sequence[str],
    runs: Iterable[Mapping[str, Any]],
    *,
    base_branch: str,
    required_workflows: Sequence[str] = DEFAULT_REQUIRED_WORKFLOWS,
) -> MergeDecision:
    reasons: list[str] = []
    head_sha = str(pr.get("headRefOid") or "")
    author = pr.get("author")
    login = author.get("login") if isinstance(author, Mapping) else None

    if login != "dependabot[bot]":
        reasons.append("untrusted_author")
    head_ref = pr.get("headRefName")
    if not isinstance(head_ref, str) or not head_ref.startswith("dependabot/"):
        reasons.append("untrusted_head")
    if pr.get("baseRefName") != base_branch:
        reasons.append("wrong_base")
    if pr.get("state") != "OPEN" or pr.get("isDraft") is not False:
        reasons.append("not_open_ready_pr")
    if pr.get("mergeable") != "MERGEABLE":
        reasons.append("not_mergeable")
    if not head_sha:
        reasons.append("missing_head_sha")

    if not files:
        reasons.append("empty_diff")
    elif any(not dependency_path_allowed(path) for path in files):
        reasons.append("out_of_scope_file")

    required = tuple(name.strip() for name in required_workflows if isinstance(name, str) and name.strip())
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
    fields = ("number", "headRefOid", "headRefName", "baseRefName", "state", "isDraft")
    if any(before.get(field) != after.get(field) for field in fields):
        return False
    before_author = before.get("author")
    after_author = after.get("author")
    before_login = before_author.get("login") if isinstance(before_author, Mapping) else None
    after_login = after_author.get("login") if isinstance(after_author, Mapping) else None
    return before_login == after_login == "dependabot[bot]"


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
        payload = self._json([
            "pr", "list", "--repo", self.repo, "--state", "open", "--limit", "100",
            "--json", "number,author,headRefName,headRefOid,baseRefName,isDraft,state,mergeable",
        ])
        return payload if isinstance(payload, list) else []

    def pr(self, number: int) -> Mapping[str, Any]:
        payload = self._json([
            "pr", "view", str(number), "--repo", self.repo,
            "--json", "number,author,headRefName,headRefOid,baseRefName,isDraft,state,mergeable",
        ])
        return payload if isinstance(payload, Mapping) else {}

    def files(self, number: int) -> list[str]:
        payload = self._json([
            "api", "--paginate", "--slurp",
            f"repos/{self.repo}/pulls/{number}/files?per_page=100",
        ])
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
        payload = self._json([
            "api", "-X", "GET", "--paginate", "--slurp",
            f"repos/{self.repo}/actions/runs?head_sha={head_sha}&event=pull_request&per_page=100",
        ])
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
        payload = self._json([
            "api", "-X", "GET", f"repos/{self.repo}/branches/{quote(branch, safe='')}"
        ])
        commit = payload.get("commit") if isinstance(payload, Mapping) else None
        sha = commit.get("sha") if isinstance(commit, Mapping) else None
        if not isinstance(sha, str) or not sha:
            raise RuntimeError("Default-branch head could not be resolved")
        return sha

    def head_contains_base(self, base_sha: str, head_sha: str) -> bool:
        if not base_sha or not head_sha:
            return False
        payload = self._json([
            "api", "-X", "GET", f"repos/{self.repo}/compare/{base_sha}...{head_sha}"
        ])
        return isinstance(payload, Mapping) and payload.get("behind_by") == 0

    def merge(self, number: int, expected_head_sha: str) -> None:
        payload = self._json([
            "api", "-X", "PUT",
            f"repos/{self.repo}/pulls/{number}/merge",
            "-f", f"sha={expected_head_sha}",
            "-f", "merge_method=squash",
        ])
        if not isinstance(payload, Mapping) or payload.get("merged") is not True:
            raise RuntimeError("Dependabot merge was not accepted")


def required_workflows_from_env() -> tuple[str, ...]:
    raw = os.getenv("DEPENDABOT_REQUIRED_WORKFLOWS", "")
    if not raw.strip():
        return DEFAULT_REQUIRED_WORKFLOWS
    values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    return values or DEFAULT_REQUIRED_WORKFLOWS


def run_once(repo: str, base_branch: str) -> int:
    client = GitHubCLI(repo)
    required = required_workflows_from_env()
    merged = 0

    for summary in client.open_prs():
        number = summary.get("number")
        if not isinstance(number, int):
            continue
        initial_base_head = client.branch_head(base_branch)
        files = client.files(number)
        runs = client.runs(str(summary.get("headRefOid") or ""))
        decision = evaluate_candidate(
            summary,
            files,
            runs,
            base_branch=base_branch,
            required_workflows=required,
        )
        if not decision.ready or not client.head_contains_base(initial_base_head, decision.head_sha):
            continue

        # Re-read all merge-relevant state, the default-branch head, and workflow
        # results immediately before mutation. A moved head/base or changed PR
        # state invalidates the pass.
        current = client.pr(number)
        current_base_head = client.branch_head(base_branch)
        if current_base_head != initial_base_head or not same_candidate_identity(summary, current):
            continue
        current_files = client.files(number)
        current_runs = client.runs(str(current.get("headRefOid") or ""))
        final = evaluate_candidate(
            current,
            current_files,
            current_runs,
            base_branch=base_branch,
            required_workflows=required,
        )
        if (
            not final.ready
            or final.head_sha != decision.head_sha
            or not client.head_contains_base(current_base_head, final.head_sha)
        ):
            continue

        # Shrink the remaining base-movement race to the final API boundary.
        # GitHub's merge API can bind the head SHA but has no expected-base-SHA
        # parameter, so any observed base movement must fail closed here.
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
