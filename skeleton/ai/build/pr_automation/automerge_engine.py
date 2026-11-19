"""Reconciliation engine for the fail-closed auto-merge control plane.

The engine performs at most one mutation from each immutable repository
snapshot.  After every mutation it discards all cached state and starts a fresh
reconciliation pass.  This prevents a successful merge from making the base SHA
of a second candidate stale inside the same decision batch.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Iterable, Sequence

from .automerge_github import GitHubAutoMergeClient
from .automerge_ledger import MergeLedger
from .automerge_model import (
    AutoMergePolicy,
    CandidateSnapshot,
    DecisionKind,
    MergeAction,
    MergeDecision,
    MergeMode,
    MutationReceipt,
    ReconcileReport,
    immutable_identity_equal,
)
from .automerge_policy import (
    classify_candidate,
    classify_paths,
    evaluate_candidate,
    sort_decisions_for_execution,
)
from .automerge_stack import (
    StackGraph,
    annotate_snapshot,
    build_stack_graph,
    landing_plan,
    validate_graph,
)


@dataclass(frozen=True, slots=True)
class EngineConfig:
    dispatch_post_merge: bool = True
    post_merge_workflows: tuple[str, ...] = (
        "merge-readiness.yml",
        "queue-drain.yml",
    )
    stop_after_stack_mutation: bool = True
    fail_on_graph_error: bool = True

    def __post_init__(self) -> None:
        if len(set(self.post_merge_workflows)) != len(self.post_merge_workflows):
            raise ValueError("duplicate post-merge workflow")


@dataclass(frozen=True, slots=True)
class IterationSnapshot:
    base_head: str
    candidates: tuple[CandidateSnapshot, ...]
    graph: StackGraph
    decisions: tuple[MergeDecision, ...]


@dataclass(frozen=True, slots=True)
class MutationSelection:
    decision: MergeDecision
    action: MergeAction
    snapshot: CandidateSnapshot


def _enrich_candidate(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
) -> CandidateSnapshot:
    classification = classify_paths(snapshot.diff.files, policy)
    return replace(
        snapshot,
        candidate_class=classify_candidate(snapshot, policy),
        sensitive_paths=classification.sensitive,
        risk_tier=classification.risk,
    )


def _candidate_map(
    candidates: Sequence[CandidateSnapshot],
) -> dict[int, CandidateSnapshot]:
    return {candidate.identity.number: candidate for candidate in candidates}


def build_iteration(
    client: GitHubAutoMergeClient,
    policy: AutoMergePolicy,
    *,
    now: datetime | None = None,
) -> IterationSnapshot:
    base_head = client.branch_head(policy.default_branch)
    raw = client.snapshots(limit=policy.budget.max_open_pr_scan)
    enriched = tuple(_enrich_candidate(item, policy) for item in raw)
    graph = build_stack_graph(enriched, default_branch=policy.default_branch)
    graph_errors = validate_graph(graph)

    annotated = tuple(annotate_snapshot(item, graph) for item in enriched)
    decisions: list[MergeDecision] = []
    for candidate in annotated:
        decision = evaluate_candidate(
            candidate,
            policy,
            now=now,
        )
        node = graph.node(candidate.identity.number)
        topology_reasons: list[str] = []
        if (
            node is not None
            and node.relation.value == "root"
            and candidate.identity.base_ref == policy.default_branch
            and candidate.identity.base_sha != base_head
        ):
            topology_reasons.append(
                "default_branch_head_moved_since_candidate_snapshot"
            )
        if (
            node is not None
            and node.relation.value == "child"
            and node.parent_pr is not None
        ):
            parent = graph.node(node.parent_pr)
            if parent is None:
                topology_reasons.append("stack_parent_missing_at_evaluation")
            elif node.base_sha != parent.head_sha:
                topology_reasons.append("stack_parent_head_moved_since_candidate_snapshot")

        if graph_errors and policy.allow_stack_child_merge and node is not None:
            if (
                node.number in graph.orphans
                or node.relation.value == "cycle"
                or any(
                    node.head_ref == branch or node.base_ref == branch
                    for branch in graph.duplicate_heads
                )
            ):
                topology_reasons.extend(graph_errors)

        if topology_reasons:
            decision = MergeDecision(
                pr_number=decision.pr_number,
                kind=DecisionKind.HOLD,
                reasons=(*decision.reasons, *tuple(dict.fromkeys(topology_reasons))),
                gates=decision.gates,
                actions=(),
                snapshot_fingerprint=decision.snapshot_fingerprint,
                policy_fingerprint=decision.policy_fingerprint,
                risk_tier=decision.risk_tier,
            )
        decisions.append(decision)

    return IterationSnapshot(
        base_head=base_head,
        candidates=annotated,
        graph=graph,
        decisions=sort_decisions_for_execution(decisions),
    )


def _eligible_stack_numbers(
    iteration: IterationSnapshot,
) -> tuple[int, ...]:
    return tuple(
        decision.pr_number
        for decision in iteration.decisions
        if decision.kind is DecisionKind.MERGE_STACK_CHILD and decision.actions
    )


def select_mutation(
    iteration: IterationSnapshot,
    policy: AutoMergePolicy,
    *,
    root_merges_used: int,
    stack_merges_used: int,
) -> MutationSelection | None:
    by_number = _candidate_map(iteration.candidates)

    if stack_merges_used < policy.budget.max_stack_merges:
        plan = landing_plan(
            iteration.graph,
            eligible=_eligible_stack_numbers(iteration),
            max_stack_merges=1,
        )
        if plan.steps:
            step = plan.steps[0]
            decision = next(
                (
                    item
                    for item in iteration.decisions
                    if item.pr_number == step.pr_number
                    and item.kind is DecisionKind.MERGE_STACK_CHILD
                ),
                None,
            )
            snapshot = by_number.get(step.pr_number)
            if decision is not None and decision.actions and snapshot is not None:
                return MutationSelection(
                    decision=decision,
                    action=decision.actions[0],
                    snapshot=snapshot,
                )

    if root_merges_used >= policy.budget.max_merges:
        return None

    for decision in iteration.decisions:
        if decision.kind not in {
            DecisionKind.MERGE,
            DecisionKind.ENABLE_AUTO_MERGE,
        }:
            continue
        if not decision.actions:
            continue
        snapshot = by_number.get(decision.pr_number)
        if snapshot is None:
            continue
        return MutationSelection(
            decision=decision,
            action=decision.actions[0],
            snapshot=snapshot,
        )
    return None


def _snapshot_matches(
    original: CandidateSnapshot,
    current: CandidateSnapshot,
) -> bool:
    return (
        immutable_identity_equal(original.identity, current.identity)
        and original.diff == current.diff
        and original.labels == current.labels
        and original.unresolved_threads == current.unresolved_threads
        and original.reviews == current.reviews
    )


def _revalidate_selection(
    client: GitHubAutoMergeClient,
    selection: MutationSelection,
    policy: AutoMergePolicy,
    *,
    expected_default_head: str,
    now: datetime | None = None,
) -> MutationSelection | None:
    """Re-read every merge-relevant input immediately before mutation."""
    original = selection.snapshot
    current = client.snapshot(original.identity.number)
    current = _enrich_candidate(current, policy)

    # The base ref of a stack child is not the default branch.  The exact
    # default head is still bound to the decision because stack mutations must
    # never race an unrelated integration change.
    if client.branch_head(policy.default_branch) != expected_default_head:
        return None

    if not _snapshot_matches(original, current):
        return None

    if original.stack_relation.value == "child":
        if original.parent_pr is None:
            return None
        try:
            parent = client.snapshot(original.parent_pr)
        except Exception:
            return None
        if (
            current.identity.base_ref != parent.identity.head_ref
            or current.identity.base_sha != parent.identity.head_sha
        ):
            return None

    # Preserve the topology annotations from the immutable pass only after
    # proving PR identity, diff evidence, and any stack-parent head did not change.
    current = replace(
        current,
        stack_relation=original.stack_relation,
        parent_pr=original.parent_pr,
    )
    decision = evaluate_candidate(
        current,
        policy,
        now=now,
    )
    if decision.kind != selection.decision.kind or not decision.actions:
        return None
    action = decision.actions[0]
    if action.expected_head_sha != selection.action.expected_head_sha:
        return None
    if action.expected_base_sha != selection.action.expected_base_sha:
        return None
    return MutationSelection(
        decision=decision,
        action=action,
        snapshot=current,
    )


def _execute(
    client: GitHubAutoMergeClient,
    selection: MutationSelection,
    policy: AutoMergePolicy,
) -> MutationReceipt:
    action = selection.action
    if action.kind is DecisionKind.ENABLE_AUTO_MERGE:
        return client.enable_native_auto_merge(
            action.pr_number,
            expected_head_sha=action.expected_head_sha,
            method=action.merge_method,
        )
    if action.kind in {DecisionKind.MERGE, DecisionKind.MERGE_STACK_CHILD}:
        return client.merge(
            action.pr_number,
            expected_head_sha=action.expected_head_sha,
            method=action.merge_method,
        )
    raise ValueError(f"unsupported mutating action: {action.kind}")


def _dispatch_post_merge(
    client: GitHubAutoMergeClient,
    *,
    default_branch: str,
    workflow_files: Iterable[str],
) -> None:
    for workflow in workflow_files:
        client.dispatch_workflow(
            workflow,
            ref=default_branch,
        )


def reconcile(
    client: GitHubAutoMergeClient,
    policy: AutoMergePolicy,
    *,
    ledger: MergeLedger | None = None,
    config: EngineConfig | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ReconcileReport:
    ledger = ledger or MergeLedger()
    config = config or EngineConfig()
    clock = clock or (lambda: datetime.now(timezone.utc))

    started = clock()
    initial_head = client.branch_head(policy.default_branch)
    decisions_seen: dict[tuple[int, str], MergeDecision] = {}
    receipts: list[MutationReceipt] = []
    root_merges_used = 0
    stack_merges_used = 0
    scanned = 0

    max_iterations = (
        policy.budget.max_merges
        + policy.budget.max_stack_merges
        + 2
    )

    for _iteration_number in range(max_iterations):
        now = clock()
        iteration = build_iteration(client, policy, now=now)
        scanned = max(scanned, len(iteration.candidates))

        graph_errors = validate_graph(iteration.graph)
        if graph_errors and config.fail_on_graph_error:
            # Graph defects only block stack mutations. Root PR decisions remain
            # useful evidence, but selection below cannot choose a corrupt child.
            pass

        for decision in iteration.decisions:
            key = (decision.pr_number, decision.snapshot_fingerprint)
            if key not in decisions_seen:
                decisions_seen[key] = decision
                ledger.append_decision(decision)

        if policy.mode is MergeMode.OBSERVE:
            break

        selection = select_mutation(
            iteration,
            policy,
            root_merges_used=root_merges_used,
            stack_merges_used=stack_merges_used,
        )
        if selection is None:
            break

        if ledger.has_action_key(selection.action.idempotency_key):
            # Durable/replayed workers must never repeat the same mutation.
            break

        current = _revalidate_selection(
            client,
            selection,
            policy,
            expected_default_head=iteration.base_head,
            now=clock(),
        )
        if current is None:
            # Repository moved between evaluation and mutation. Discard the
            # entire snapshot and attempt one fresh pass.
            continue

        receipt = _execute(client, current, policy)
        receipt = replace(
            receipt,
            action_key=current.action.idempotency_key,
        )
        receipts.append(receipt)
        ledger.append_receipt(receipt)

        if current.action.kind is DecisionKind.MERGE_STACK_CHILD:
            stack_merges_used += 1
            if config.stop_after_stack_mutation:
                break
            continue

        if current.action.kind in {
            DecisionKind.MERGE,
            DecisionKind.ENABLE_AUTO_MERGE,
        }:
            root_merges_used += 1
            if receipt.merged and config.dispatch_post_merge:
                _dispatch_post_merge(
                    client,
                    default_branch=policy.default_branch,
                    workflow_files=config.post_merge_workflows,
                )

        # A successful direct merge changes the default head; native auto-merge
        # may merge immediately or remain queued. Either way, the next pass
        # re-reads all repository state and exact-head evidence.
        if root_merges_used >= policy.budget.max_merges:
            break

    final_head = client.branch_head(policy.default_branch)
    if final_head != initial_head:
        ledger.append_base_transition(
            before=initial_head,
            after=final_head,
            reason="auto-merge reconciliation mutated default branch",
        )

    finished = clock()
    return ReconcileReport(
        repository=client.repository,
        default_branch=policy.default_branch,
        policy_fingerprint=policy.fingerprint(),
        scanned=scanned,
        decisions=tuple(decisions_seen.values()),
        receipts=tuple(receipts),
        base_head_before=initial_head,
        base_head_after=final_head,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
    )


def report_markdown(report: ReconcileReport) -> str:
    lines = [
        "# Auto-merge reconciliation",
        "",
        f"- Repository: `{report.repository}`",
        f"- Default branch: `{report.default_branch}`",
        f"- Policy: `{report.policy_fingerprint}`",
        f"- Base before: `{report.base_head_before}`",
        f"- Base after: `{report.base_head_after}`",
        f"- Candidates scanned: {report.scanned}",
        f"- Decisions captured: {len(report.decisions)}",
        f"- Mutations attempted: {len(report.receipts)}",
        "",
        "## Decisions",
        "",
        "| PR | Decision | Risk | Reasons |",
        "| ---: | --- | --- | --- |",
    ]
    for decision in sorted(report.decisions, key=lambda item: item.pr_number):
        reasons = "; ".join(decision.reasons).replace("|", "\\|")
        lines.append(
            f"| #{decision.pr_number} | {decision.kind.value} | "
            f"{decision.risk_tier.value} | {reasons} |"
        )

    lines.extend(
        [
            "",
            "## Mutations",
            "",
            "| PR | Merged | Merge SHA | Message |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for receipt in report.receipts:
        message = receipt.message.replace("|", "\\|")
        lines.append(
            f"| #{receipt.pr_number} | {str(receipt.merged).lower()} | "
            f"`{receipt.merge_sha or '-'}` | {message} |"
        )
    return "\n".join(lines) + "\n"


def decisions_by_kind(
    report: ReconcileReport,
) -> dict[DecisionKind, tuple[MergeDecision, ...]]:
    grouped: dict[DecisionKind, list[MergeDecision]] = {
        kind: [] for kind in DecisionKind
    }
    for decision in report.decisions:
        grouped[decision.kind].append(decision)
    return {
        kind: tuple(sorted(items, key=lambda item: item.pr_number))
        for kind, items in grouped.items()
    }


def mutation_success_count(report: ReconcileReport) -> int:
    return sum(receipt.merged for receipt in report.receipts)


def mutation_failure_count(report: ReconcileReport) -> int:
    return sum(not receipt.merged for receipt in report.receipts)


def assert_report_consistent(report: ReconcileReport) -> None:
    decision_prs = {decision.pr_number for decision in report.decisions}
    for receipt in report.receipts:
        if receipt.pr_number not in decision_prs:
            raise ValueError(
                f"mutation receipt for PR #{receipt.pr_number} has no decision evidence"
            )
    if report.base_head_before != report.base_head_after and not any(
        receipt.merged for receipt in report.receipts
    ):
        raise ValueError("default branch changed without a recorded successful merge")


__all__ = [
    "EngineConfig",
    "IterationSnapshot",
    "MutationSelection",
    "assert_report_consistent",
    "build_iteration",
    "decisions_by_kind",
    "mutation_failure_count",
    "mutation_success_count",
    "reconcile",
    "report_markdown",
    "select_mutation",
]
