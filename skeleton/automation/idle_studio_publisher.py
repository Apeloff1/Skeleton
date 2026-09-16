"""Credential-isolated publisher for reviewed Idle Studio packages.

The model key must be absent. This module revalidates the sealed package,
checks current task claims and PR capacity, checks the main SHA both before and
after Git object construction, and only then creates a review branch and PR.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence

from .idle_studio import (
    ChangeProposal,
    StudioConfig,
    WorkItem,
    WorkerSpec,
    GitHubClient,
    _existing_studio_task_keys,
    _open_studio_pr_count,
    _proposal_body,
    task_fingerprint,
)
from .idle_studio_v2 import ReviewDecision, read_package, unpack_entry


class PublisherClient(Protocol):
    def open_pulls(self) -> list[Mapping[str, Any]]: ...
    def branch_sha(self, branch: str) -> str: ...
    def commit_tree_sha(self, commit_sha: str) -> str: ...
    def create_blob(self, content: str) -> str: ...
    def create_tree(self, base_tree: str, blobs: Sequence[tuple[str, str]]) -> str: ...
    def create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str: ...
    def create_ref(self, branch: str, sha: str) -> None: ...
    def create_pull(self, *, title: str, branch: str, body: str) -> Mapping[str, Any]: ...


def branch_name(task: WorkItem, builder: WorkerSpec, run_id: str, attempt: str) -> str:
    identity = f"{run_id or 'local'}-{attempt or '1'}"
    suffix = re.sub(r"[^0-9A-Za-z-]", "", identity)[-20:] or "local-1"
    return f"idle-studio/{builder.worker_id}/{task_fingerprint(task)}-{suffix}"


def _review_body(
    task: WorkItem,
    builder: WorkerSpec,
    reviewer: WorkerSpec,
    review: ReviewDecision,
    proposal: ChangeProposal,
) -> str:
    return _proposal_body(task, builder, proposal) + (
        "\n\n### Independent senior review\n"
        f"- Reviewer: `{reviewer.worker_id}` ({reviewer.role})\n"
        "- Decision: approved for CI\n"
        f"- Reason: {review.reason or 'approved'}\n"
    )


def publish_entries(
    package: Mapping[str, Any],
    config: StudioConfig,
    github: PublisherClient,
    *,
    run_id: str,
    attempt: str,
) -> list[dict[str, Any]]:
    base_sha = str(package.get("base_sha", ""))
    entries = package.get("entries", [])
    if not base_sha or not isinstance(entries, list):
        raise ValueError("invalid package")

    fresh_pulls = github.open_pulls()
    claimed = _existing_studio_task_keys(fresh_pulls)
    capacity = max(
        0,
        config.max_open_studio_prs - _open_studio_pr_count(fresh_pulls),
    )
    published: list[dict[str, Any]] = []

    for raw in entries:
        if len(published) >= capacity:
            break
        if not isinstance(raw, Mapping):
            raise ValueError("package entry must be an object")
        task, builder, reviewer, review, proposal = unpack_entry(raw, config)
        if task.key in claimed:
            continue

        title = f"bot({builder.role}): {task.title}"[:240]
        branch = branch_name(task, builder, run_id, attempt)
        body = _review_body(task, builder, reviewer, review, proposal)

        if github.branch_sha("main") != base_sha:
            raise RuntimeError("main moved before idle-studio publication")
        base_tree = github.commit_tree_sha(base_sha)
        blobs = [
            (item.path, github.create_blob(item.content))
            for item in proposal.files
        ]
        tree_sha = github.create_tree(base_tree, blobs)
        commit_sha = github.create_commit(title, tree_sha, base_sha)

        if github.branch_sha("main") != base_sha:
            raise RuntimeError("main moved at final idle-studio branch boundary")
        github.create_ref(branch, commit_sha)

        if github.branch_sha("main") != base_sha:
            raise RuntimeError(
                "main moved after idle-studio branch creation; refusing PR creation"
            )
        pr = github.create_pull(title=title, branch=branch, body=body)
        claimed.add(task.key)
        published.append(
            {
                "task": task.key,
                "number": pr.get("number"),
                "url": pr.get("html_url"),
                "branch": branch,
            }
        )

    return published


def publish(package_path: Path, config: StudioConfig) -> int:
    if os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("OPENAI_API_KEY must be absent during publish")
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.environ.pop("GITHUB_TOKEN", "").strip() or os.environ.pop(
        "GH_TOKEN", ""
    ).strip()
    if not repo or not token:
        raise ValueError("GitHub repository/token required")

    package = read_package(package_path)
    github = GitHubClient(repo, token)
    published = publish_entries(
        package,
        config,
        github,
        run_id=os.getenv("GITHUB_RUN_ID", "local"),
        attempt=os.getenv("GITHUB_RUN_ATTEMPT", "1"),
    )
    print(
        json.dumps(
            {
                "status": "published",
                "count": len(published),
                "pull_requests": published,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    return publish(Path(args.package), StudioConfig.from_env())


if __name__ == "__main__":
    raise SystemExit(main())
