"""Credential-isolated publisher for reviewed Idle Studio packages.

The model key must be absent. This module revalidates the sealed four-agent
package, checks current task claims and PR capacity, checks the main SHA before
and after Git object construction, and only then creates a review branch and PR.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .chatgpt_adapter import require_repository_provider_credentials_absent
from .idle_studio import (
    ChangeProposal,
    GitHubClient,
    GitHubError,
    StudioConfig,
    WorkItem,
    WorkerSpec,
    _existing_studio_task_keys,
    _open_studio_pr_count,
    _proposal_body,
    canonical_commit_oid,
    task_fingerprint,
)
from .idle_studio_v2 import (
    IdleTaskSquad,
    ResearchDecision,
    ReviewDecision,
    VerificationDecision,
    read_package,
    unpack_entry,
)


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
    squad: IdleTaskSquad,
    research: ResearchDecision,
    review: ReviewDecision,
    verification: VerificationDecision,
    proposal: ChangeProposal,
) -> str:
    findings = "\n".join(f"  - {item}" for item in research.findings[:5]) or "  - No additional finding recorded."
    checks = "\n".join(f"  - {item}" for item in verification.required_checks[:10]) or "  - Repository CI."
    return _proposal_body(task, squad.builder, proposal) + (
        "\n\n### Four-agent squad provenance\n"
        f"- Researcher: `{squad.researcher.worker_id}` ({squad.researcher.role})\n"
        f"- Lead: `{squad.builder.worker_id}` ({squad.builder.role})\n"
        f"- Reviewer: `{squad.reviewer.worker_id}` ({squad.reviewer.role})\n"
        f"- Verifier: `{squad.verifier.worker_id}` ({squad.verifier.role})\n"
        f"- Review decision: approved for CI — {review.reason or 'approved'}\n"
        f"- Verification decision: approved for credential-free CI — {verification.reason or 'approved'}\n\n"
        "### Research findings\n"
        f"{findings}\n\n"
        "### Required deterministic checks\n"
        f"{checks}\n"
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
    try:
        base_sha = canonical_commit_oid(base_sha)
    except GitHubError as exc:
        raise ValueError("invalid package") from exc

    fresh_pulls = github.open_pulls()
    claimed = _existing_studio_task_keys(fresh_pulls)
    capacity = max(0, config.max_open_studio_prs - _open_studio_pr_count(fresh_pulls))
    prepared: list[
        tuple[
            WorkItem,
            IdleTaskSquad,
            ResearchDecision,
            ReviewDecision,
            VerificationDecision,
            ChangeProposal,
        ]
    ] = []
    path_owners: dict[str, str] = {}
    worker_owners: dict[str, str] = {}
    scheduled_tasks = set(claimed)

    # Preflight the complete publishable batch before creating any blob, branch,
    # or pull request. Different squads may not share workers or write the same
    # repository path in one run; either condition is an anti-swarm violation.
    for raw in entries:
        if len(prepared) >= capacity:
            break
        if not isinstance(raw, Mapping):
            raise ValueError("package entry must be an object")
        task, squad, research, review, verification, proposal = unpack_entry(raw, config)
        if task.key in scheduled_tasks:
            continue

        proposal_paths = tuple(item.path for item in proposal.files)
        overlapping = sorted(path for path in proposal_paths if path in path_owners)
        if overlapping:
            prior = {path: path_owners[path] for path in overlapping}
            raise ValueError(
                f"idle-studio squads overlap repository paths: {prior!r} conflicts with {task.key!r}"
            )

        reused_workers = sorted(worker_id for worker_id in squad.worker_ids if worker_id in worker_owners)
        if reused_workers:
            prior = {worker_id: worker_owners[worker_id] for worker_id in reused_workers}
            raise ValueError(
                f"idle-studio squads reuse workers across tasks: {prior!r} conflicts with {task.key!r}"
            )

        for path in proposal_paths:
            path_owners[path] = task.key
        for worker_id in squad.worker_ids:
            worker_owners[worker_id] = task.key
        scheduled_tasks.add(task.key)
        prepared.append((task, squad, research, review, verification, proposal))

    published: list[dict[str, Any]] = []
    for task, squad, research, review, verification, proposal in prepared:
        title = f"bot({squad.builder.role}): {task.title}"[:240]
        branch = branch_name(task, squad.builder, run_id, attempt)
        body = _review_body(task, squad, research, review, verification, proposal)

        if github.branch_sha("main") != base_sha:
            raise RuntimeError("main moved before idle-studio publication")
        base_tree = github.commit_tree_sha(base_sha)
        blobs = [(item.path, github.create_blob(item.content)) for item in proposal.files]
        tree_sha = github.create_tree(base_tree, blobs)
        commit_sha = github.create_commit(title, tree_sha, base_sha)

        if github.branch_sha("main") != base_sha:
            raise RuntimeError("main moved at final idle-studio branch boundary")
        github.create_ref(branch, commit_sha)

        if github.branch_sha("main") != base_sha:
            raise RuntimeError("main moved after idle-studio branch creation; refusing PR creation")
        pr = github.create_pull(title=title, branch=branch, body=body)
        published.append(
            {
                "task": task.key,
                "number": pr.get("number"),
                "url": pr.get("html_url"),
                "branch": branch,
                "squad": list(squad.worker_ids),
            }
        )

    return published


def publish(package_path: Path, config: StudioConfig) -> int:
    require_repository_provider_credentials_absent()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.environ.pop("GITHUB_TOKEN", "").strip() or os.environ.pop("GH_TOKEN", "").strip()
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
            {"status": "published", "count": len(published), "pull_requests": published},
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
