"""Shared deterministic fixtures for auto-merge regression tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from skeleton.pr_automation.automerge_model import (
    AutoMergePolicy,
    CandidateClass,
    CandidateSnapshot,
    DiffSummary,
    GateRequirement,
    MergeBudget,
    MergeMethod,
    MergeMode,
    PullRequestIdentity,
    ReviewEvidence,
    RiskTier,
    StackRelation,
    WorkflowEvidence,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
SHA_E = "e" * 40
SHA_F = "f" * 40
NOW = datetime(2026, 9, 19, 20, 0, tzinfo=timezone.utc)


BASE_WORKFLOWS = (
    "CI/CD",
    "Merge Readiness",
    "Secret scanning",
    "Malware Gate",
    "Repository Hygiene Gate",
    "Artifact Policy",
    "Provenance Policy",
    "PR Hygiene",
)


CODE_WORKFLOWS = (
    "Backend Quality",
    "Frontier Contracts",
    "ARM64 Ubuntu Validation",
)


def identity(
    *,
    number: int = 1,
    base_ref: str = "main",
    base_sha: str = SHA_A,
    head_ref: str = "feature/example",
    head_sha: str = SHA_B,
    author: str = "Apeloff1",
    state: str = "open",
    draft: bool = False,
    head_repo: str = "Apeloff1/Skeleton",
    mergeable: bool | None = True,
    mergeable_state: str = "clean",
) -> PullRequestIdentity:
    return PullRequestIdentity(
        repository="Apeloff1/Skeleton",
        number=number,
        node_id=f"PR_node_{number}",
        state=state,
        draft=draft,
        author=author,
        base_ref=base_ref,
        base_sha=base_sha,
        head_ref=head_ref,
        head_sha=head_sha,
        head_repo=head_repo,
        mergeable=mergeable,
        mergeable_state=mergeable_state,
        created_at="2026-09-19T18:00:00Z",
        updated_at="2026-09-19T19:00:00Z",
    )


def workflow(
    name: str,
    *,
    head_sha: str = SHA_B,
    run_id: int = 1,
    run_number: int = 1,
    attempt: int = 1,
    event: str = "pull_request",
    status: str = "completed",
    conclusion: str | None = "success",
    updated_at: datetime | None = None,
) -> WorkflowEvidence:
    timestamp = updated_at or (NOW - timedelta(minutes=5))
    return WorkflowEvidence(
        name=name,
        run_id=run_id,
        run_number=run_number,
        attempt=attempt,
        head_sha=head_sha,
        event=event,
        status=status,
        conclusion=conclusion,
        created_at=(timestamp - timedelta(minutes=1)).isoformat(),
        updated_at=timestamp.isoformat(),
        html_url=f"https://example.invalid/runs/{run_id}",
    )


def successful_runs(
    names: Iterable[str] = BASE_WORKFLOWS,
    *,
    head_sha: str = SHA_B,
    start_id: int = 1,
    updated_at: datetime | None = None,
) -> tuple[WorkflowEvidence, ...]:
    return tuple(
        workflow(
            name,
            head_sha=head_sha,
            run_id=start_id + index,
            run_number=100 + index,
            updated_at=updated_at,
        )
        for index, name in enumerate(names)
    )


def reviews(
    *,
    approvals: int = 0,
    changes_requested: int = 0,
) -> tuple[ReviewEvidence, ...]:
    items: list[ReviewEvidence] = []
    for index in range(approvals):
        items.append(
            ReviewEvidence(
                login=f"approver-{index}",
                state="APPROVED",
                submitted_at=(
                    NOW - timedelta(minutes=10 - index)
                ).isoformat(),
                commit_id=SHA_B,
            )
        )
    for index in range(changes_requested):
        items.append(
            ReviewEvidence(
                login=f"blocker-{index}",
                state="CHANGES_REQUESTED",
                submitted_at=(
                    NOW - timedelta(minutes=8 - index)
                ).isoformat(),
                commit_id=SHA_B,
            )
        )
    return tuple(items)


def snapshot(
    *,
    number: int = 1,
    base_ref: str = "main",
    base_sha: str = SHA_A,
    head_ref: str = "feature/example",
    head_sha: str = SHA_B,
    author: str = "Apeloff1",
    files: Sequence[str] = ("docs/example.md",),
    additions: int = 10,
    deletions: int = 2,
    labels: Sequence[str] = ("automerge",),
    run_names: Sequence[str] = BASE_WORKFLOWS,
    workflow_runs: Sequence[WorkflowEvidence] | None = None,
    review_items: Sequence[ReviewEvidence] = (),
    unresolved_threads: int | None = 0,
    state: str = "open",
    draft: bool = False,
    head_repo: str = "Apeloff1/Skeleton",
    mergeable: bool | None = True,
    mergeable_state: str = "clean",
    head_contains_base: bool | None = True,
    stack_relation: StackRelation = StackRelation.ROOT,
    parent_pr: int | None = None,
    candidate_class: CandidateClass = CandidateClass.OWNER,
    sensitive_paths: Sequence[str] = (),
    risk_tier: RiskTier = RiskTier.LOW,
) -> CandidateSnapshot:
    ident = identity(
        number=number,
        base_ref=base_ref,
        base_sha=base_sha,
        head_ref=head_ref,
        head_sha=head_sha,
        author=author,
        state=state,
        draft=draft,
        head_repo=head_repo,
        mergeable=mergeable,
        mergeable_state=mergeable_state,
    )
    runs = (
        tuple(workflow_runs)
        if workflow_runs is not None
        else successful_runs(
            run_names,
            head_sha=head_sha,
        )
    )
    return CandidateSnapshot(
        identity=ident,
        diff=DiffSummary(
            files=tuple(files),
            additions=additions,
            deletions=deletions,
            changed_files=len(files),
        ),
        labels=tuple(labels),
        reviews=tuple(review_items),
        unresolved_threads=unresolved_threads,
        workflow_runs=runs,
        head_contains_base=head_contains_base,
        candidate_class=candidate_class,
        stack_relation=stack_relation,
        parent_pr=parent_pr,
        sensitive_paths=tuple(sensitive_paths),
        risk_tier=risk_tier,
        captured_at=NOW.isoformat(),
    )


def policy(
    *,
    mode: MergeMode = MergeMode.MERGE_DIRECT,
    required: Sequence[str] = BASE_WORKFLOWS,
    approvals: int = 0,
    stability_seconds: int = 30,
    max_merges: int = 3,
    max_stack_merges: int = 2,
    max_changed_files: int = 250,
    max_line_delta: int = 20_000,
    allow_owner_without_opt_in: bool = True,
    allow_dependabot_without_opt_in: bool = True,
    allow_stack_child_merge: bool = True,
) -> AutoMergePolicy:
    return AutoMergePolicy(
        default_branch="main",
        mode=mode,
        merge_method=MergeMethod.SQUASH,
        required_workflows=tuple(GateRequirement(name) for name in required),
        required_approvals=approvals,
        owner_logins=("apeloff1",),
        trusted_bot_logins=("dependabot[bot]",),
        allow_owner_without_opt_in=allow_owner_without_opt_in,
        allow_dependabot_without_opt_in=allow_dependabot_without_opt_in,
        allow_stack_child_merge=allow_stack_child_merge,
        budget=MergeBudget(
            max_merges=max_merges,
            max_stack_merges=max_stack_merges,
            max_changed_files=max_changed_files,
            max_line_delta=max_line_delta,
            stability_seconds=stability_seconds,
            max_open_pr_scan=250,
        ),
    )


def with_run_state(
    candidate: CandidateSnapshot,
    name: str,
    *,
    status: str,
    conclusion: str | None,
    run_number: int = 999,
    attempt: int = 1,
    updated_at: datetime | None = None,
) -> CandidateSnapshot:
    kept = tuple(run for run in candidate.workflow_runs if run.name != name)
    changed = workflow(
        name,
        head_sha=candidate.identity.head_sha,
        run_id=50_000 + run_number,
        run_number=run_number,
        attempt=attempt,
        status=status,
        conclusion=conclusion,
        updated_at=updated_at,
    )
    return replace(candidate, workflow_runs=(*kept, changed))


def with_extra_run(
    candidate: CandidateSnapshot,
    run: WorkflowEvidence,
) -> CandidateSnapshot:
    return replace(candidate, workflow_runs=(*candidate.workflow_runs, run))


def as_stack_child(
    candidate: CandidateSnapshot,
    *,
    parent_pr: int,
    base_ref: str,
    base_sha: str,
) -> CandidateSnapshot:
    ident = replace(
        candidate.identity,
        base_ref=base_ref,
        base_sha=base_sha,
    )
    return replace(
        candidate,
        identity=ident,
        stack_relation=StackRelation.CHILD,
        parent_pr=parent_pr,
    )


def require_code_workflows(candidate: CandidateSnapshot) -> CandidateSnapshot:
    existing = {run.name for run in candidate.workflow_runs}
    missing = [name for name in CODE_WORKFLOWS if name not in existing]
    runs = (
        *candidate.workflow_runs,
        *successful_runs(
            missing,
            head_sha=candidate.identity.head_sha,
            start_id=10_000,
        ),
    )
    return replace(candidate, workflow_runs=runs)


class FakeClient:
    """Small stateful GitHub client fake used by engine tests."""

    def __init__(
        self,
        candidates: Sequence[CandidateSnapshot],
        *,
        base_head: str = SHA_A,
    ) -> None:
        self.repository = "Apeloff1/Skeleton"
        self._candidates = {
            candidate.identity.number: candidate
            for candidate in candidates
        }
        self._base_head = base_head
        self.merges: list[tuple[int, str, str]] = []
        self.native: list[tuple[int, str, str]] = []
        self.dispatches: list[tuple[str, str]] = []

    def branch_head(self, branch: str) -> str:
        assert branch == "main"
        return self._base_head

    def snapshots(self, *, limit: int = 250) -> tuple[CandidateSnapshot, ...]:
        return tuple(
            self._candidates[number]
            for number in sorted(self._candidates)[:limit]
        )

    def snapshot(self, number: int) -> CandidateSnapshot:
        return self._candidates[number]

    def merge(self, number: int, *, expected_head_sha: str, method):
        from skeleton.pr_automation.automerge_model import MutationReceipt

        candidate = self._candidates[number]
        if candidate.identity.head_sha != expected_head_sha:
            return MutationReceipt(
                pr_number=number,
                action_key="fake",
                requested_head_sha=expected_head_sha,
                observed_head_sha=candidate.identity.head_sha,
                base_ref=candidate.identity.base_ref,
                merged=False,
                merge_sha=None,
                message="head mismatch",
            )
        self.merges.append((number, expected_head_sha, method.value))
        merge_sha = SHA_C if self._base_head != SHA_C else SHA_D
        if candidate.identity.base_ref == "main":
            self._base_head = merge_sha
        del self._candidates[number]
        return MutationReceipt(
            pr_number=number,
            action_key="fake",
            requested_head_sha=expected_head_sha,
            observed_head_sha=expected_head_sha,
            base_ref=candidate.identity.base_ref,
            merged=True,
            merge_sha=merge_sha,
            message="merged",
        )

    def enable_native_auto_merge(
        self,
        number: int,
        *,
        expected_head_sha: str,
        method,
    ):
        from skeleton.pr_automation.automerge_model import MutationReceipt

        candidate = self._candidates[number]
        self.native.append((number, expected_head_sha, method.value))
        return MutationReceipt(
            pr_number=number,
            action_key="fake-native",
            requested_head_sha=expected_head_sha,
            observed_head_sha=candidate.identity.head_sha,
            base_ref=candidate.identity.base_ref,
            merged=False,
            merge_sha=None,
            message="native enabled",
        )

    def dispatch_workflow(self, workflow_file: str, *, ref: str, inputs=None):
        del inputs
        self.dispatches.append((workflow_file, ref))


__all__ = [
    "BASE_WORKFLOWS",
    "CODE_WORKFLOWS",
    "FakeClient",
    "NOW",
    "SHA_A",
    "SHA_B",
    "SHA_C",
    "SHA_D",
    "SHA_E",
    "SHA_F",
    "as_stack_child",
    "identity",
    "policy",
    "require_code_workflows",
    "reviews",
    "snapshot",
    "successful_runs",
    "with_extra_run",
    "with_run_state",
    "workflow",
]
