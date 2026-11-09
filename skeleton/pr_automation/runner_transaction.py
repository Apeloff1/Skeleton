"""Mutation transaction boundary for PR automation runner v2.

This module is intentionally narrow: it is the only runner-v2 component that
performs merge mutations.  Every merge requires a durable EventIndex claim,
fresh mutation-grade evidence, exact base/head identity, protected base state,
current queue/rate observations, and a server-side expected-head SHA.

There are no automatic retries around merge PUTs.  A caller may reconcile again
from fresh state after an explicit failure, but the transaction itself is
single-shot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .core import Decision
from .index import EventIndex
from .runner_contracts import (
    MutationIntent,
    MutationReceipt,
    MutationState,
    Preconditions,
    RunnerPolicy,
    RunnerSnapshot,
    WorkItem,
    bounded_text,
    snapshot_policy_fingerprint,
    utcnow,
    valid_sha,
)
from .runner_evidence import EvidenceCollector
from .runner_scheduler import QueueObservation
from .runner_transport import (
    BudgetedGitHubTransport,
    GitHubHTTPError,
    RunnerTransportError,
)


class MutationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BranchObservation:
    head_sha: str | None
    protected: bool | None


def _time(clock: Callable[[], datetime] | None = None) -> datetime:
    moment = (clock or utcnow)()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _branch_payload(
    transport: BudgetedGitHubTransport,
    repository: str,
    branch: str,
) -> Mapping[str, Any]:
    from urllib.parse import quote

    payload = transport.get(
        f"/repos/{repository}/branches/{quote(branch, safe='')}"
    )
    if not isinstance(payload, Mapping):
        raise MutationError("branch response was not an object")
    return payload


def observe_branch(
    transport: BudgetedGitHubTransport,
    repository: str,
    branch: str,
) -> BranchObservation:
    try:
        payload = _branch_payload(transport, repository, branch)
    except RunnerTransportError:
        return BranchObservation(head_sha=None, protected=None)
    commit = payload.get("commit")
    sha = commit.get("sha") if isinstance(commit, Mapping) else None
    head_sha: str | None = None
    if isinstance(sha, str):
        candidate = sha.casefold()
        if valid_sha(candidate):
            head_sha = candidate
    raw_protected = payload.get("protected")
    protected = raw_protected if isinstance(raw_protected, bool) else None
    return BranchObservation(
        head_sha=head_sha,
        protected=protected,
    )


def branch_protected(
    transport: BudgetedGitHubTransport,
    repository: str,
    branch: str,
) -> bool | None:
    return observe_branch(transport, repository, branch).protected


def branch_head(
    transport: BudgetedGitHubTransport,
    repository: str,
    branch: str,
) -> str | None:
    return observe_branch(transport, repository, branch).head_sha


def _reviews_valid(
    original: RunnerSnapshot,
    current: RunnerSnapshot,
    policy: RunnerPolicy,
) -> bool:
    if original.core.approvals != current.core.approvals:
        return False
    if original.core.changes_requested != current.core.changes_requested:
        return False
    if original.core.unresolved_threads != current.core.unresolved_threads:
        return False
    if policy.require_latest_reviews_on_head:
        if current.core.approvals is None:
            return False
    return True


def _checks_valid(
    original: RunnerSnapshot,
    current: RunnerSnapshot,
) -> bool:
    return (
        original.required_check_states == current.required_check_states
        and current.core.ci_state == original.core.ci_state
        and current.core.ci_state.value == "passing"
    )


def _snapshot_matches(
    original: RunnerSnapshot,
    current: RunnerSnapshot,
) -> bool:
    return snapshot_policy_fingerprint(original) == snapshot_policy_fingerprint(current)


def compute_preconditions(
    *,
    original: RunnerSnapshot,
    current: RunnerSnapshot,
    policy: RunnerPolicy,
    protected: bool | None,
    observed_base_head: str | None,
    observation: QueueObservation,
    expected_policy_fingerprint: str | None = None,
    expected_snapshot_fingerprint: str | None = None,
) -> Preconditions:
    queue_ok = (
        not policy.queue_pressure_hold
        or (
            observation.queued_actions is not None
            and observation.queued_actions
            <= policy.limits.queue_pressure_threshold
        )
    )
    rate_ok = (
        observation.rate_remaining is None
        or observation.rate_remaining
        >= policy.limits.minimum_rate_remaining
    )
    protected_ok = (
        True
        if not policy.protected_base_required
        else protected is True
    )
    base_matches = (
        observed_base_head is not None
        and observed_base_head == original.core.base_sha
        and current.core.base_sha == original.core.base_sha
    )
    head_matches = current.core.head_sha == original.core.head_sha
    policy_matches = (
        expected_policy_fingerprint is None
        or expected_policy_fingerprint == policy.fingerprint()
    )
    if expected_snapshot_fingerprint is not None:
        policy_matches = (
            policy_matches
            and expected_snapshot_fingerprint
            == snapshot_policy_fingerprint(original)
        )
    return Preconditions(
        protected_base=protected_ok,
        base_head_matches=base_matches,
        head_matches=head_matches,
        snapshot_matches=_snapshot_matches(original, current),
        policy_matches=policy_matches,
        checks_still_passing=_checks_valid(original, current),
        reviews_still_valid=_reviews_valid(original, current, policy),
        queue_within_limit=queue_ok,
        rate_limit_safe=rate_ok,
    )


def compute_transaction_preconditions(
    *,
    intent: MutationIntent,
    original: RunnerSnapshot,
    current: RunnerSnapshot,
    policy: RunnerPolicy,
    protected: bool | None,
    observed_base_head: str | None,
    observation: QueueObservation,
) -> Preconditions:
    return compute_preconditions(
        original=original,
        current=current,
        policy=policy,
        protected=protected,
        observed_base_head=observed_base_head,
        observation=observation,
        expected_policy_fingerprint=intent.policy_fingerprint,
        expected_snapshot_fingerprint=intent.snapshot_fingerprint,
    )


def receipt(
    intent: MutationIntent,
    state: MutationState,
    *,
    started: datetime,
    finished: datetime,
    current: RunnerSnapshot | None = None,
    merge_sha: str | None = None,
    message: str,
    preconditions: Preconditions | None = None,
) -> MutationReceipt:
    return MutationReceipt(
        intent=intent,
        state=state,
        observed_head_sha=(
            current.core.head_sha if current is not None else None
        ),
        observed_base_sha=(
            current.core.base_sha if current is not None else None
        ),
        merge_sha=merge_sha,
        message=bounded_text(message, limit=2000),
        preconditions=preconditions,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
    )


class MergeTransaction:
    def __init__(
        self,
        transport: BudgetedGitHubTransport,
        collector: EvidenceCollector,
        index: EventIndex,
        policy: RunnerPolicy,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.transport = transport
        self.collector = collector
        self.index = index
        self.policy = policy
        self.clock = clock

    def _claim(self, intent: MutationIntent) -> bool:
        return self.index.claim_action(
            idempotency_key=intent.key,
            repository=intent.repository,
            pr_number=intent.pr_number,
            expected_head_sha=intent.expected_head_sha,
            action_kind=intent.kind.value,
        )

    def _finish(
        self,
        intent: MutationIntent,
        *,
        success: bool,
        error: str | None = None,
        uncertain: bool = False,
    ) -> None:
        self.index.finish_action(
            intent.key,
            success=success,
            error=error,
            uncertain=uncertain,
        )

    def _fresh_observation(self, repository: str) -> QueueObservation:
        queued: int | None
        try:
            queued = self.transport.queued_actions_count(repository)
        except RunnerTransportError:
            queued = None
        remaining = self.transport.minimum_rate_remaining
        return QueueObservation(
            queued_actions=queued,
            rate_remaining=remaining,
            captured_at=_time(self.clock).isoformat(),
        )

    def _validate_plan(self, item: WorkItem) -> None:
        if item.evaluation.decision is not Decision.MERGE:
            raise MutationError("work item is not a merge decision")
        if not item.evaluation.actions:
            raise MutationError("merge decision has no planned action")
        if len(item.evaluation.actions) != 1:
            raise MutationError("runner v2 requires one atomic merge action")
        action = item.evaluation.actions[0]
        if action.kind != "merge":
            raise MutationError(f"unsupported action kind: {action.kind}")
        if action.expected_head_sha != item.snapshot.core.head_sha:
            raise MutationError("planned action expected head does not match snapshot")

    def apply(self, item: WorkItem) -> MutationReceipt:
        self._validate_plan(item)
        intent = MutationIntent.from_work_item(item, self.policy)
        started = _time(self.clock)

        if not self._claim(intent):
            return receipt(
                intent,
                MutationState.DUPLICATE,
                started=started,
                finished=_time(self.clock),
                current=item.snapshot,
                message="idempotency claim already exists",
            )

        mutation_dispatched = False
        try:
            current = self.collector.refresh_policy_fields(item.snapshot)
            branch_state = observe_branch(
                self.transport,
                item.snapshot.core.repository,
                item.snapshot.core.base_ref,
            )
            observed_base = branch_state.head_sha
            protected = branch_state.protected
            observation = self._fresh_observation(
                item.snapshot.core.repository
            )
            preconditions = compute_transaction_preconditions(
                intent=intent,
                original=item.snapshot,
                current=current,
                policy=self.policy,
                protected=protected,
                observed_base_head=observed_base,
                observation=observation,
            )
            if not preconditions.satisfied:
                message = (
                    "mutation preconditions failed: "
                    + ",".join(preconditions.failed())
                )
                self._finish(intent, success=False, error=message)
                return receipt(
                    intent,
                    MutationState.ABORTED,
                    started=started,
                    finished=_time(self.clock),
                    current=current,
                    message=message,
                    preconditions=preconditions,
                )

            # Fresh mutation-grade evidence and queue observation may consume
            # the final read-budget slot. Do not classify a request-budget
            # rejection as an ambiguous merge dispatch: no mutation request
            # has been attempted yet, so this remains safely retriable.
            if self.transport.request_count >= self.policy.limits.max_requests:
                message = "mutation request budget exhausted before dispatch"
                self._finish(intent, success=False, error=message)
                return receipt(
                    intent,
                    MutationState.ABORTED,
                    started=started,
                    finished=_time(self.clock),
                    current=current,
                    message=message,
                    preconditions=preconditions,
                )

            mutation_dispatched = True
            result = self.transport.put(
                f"/repos/{intent.repository}/pulls/{intent.pr_number}/merge",
                {
                    "sha": intent.expected_head_sha,
                    "merge_method": intent.merge_method,
                },
                retry_safe=False,
            )
            if not isinstance(result, Mapping):
                raise MutationError("merge response was not an object")
            if result.get("merged") is not True:
                message = str(result.get("message") or "merge rejected")
                self._finish(intent, success=False, error=message)
                return receipt(
                    intent,
                    MutationState.REJECTED,
                    started=started,
                    finished=_time(self.clock),
                    current=current,
                    message=message,
                    preconditions=preconditions,
                )

            raw_merge_sha = result.get("sha")
            merge_sha = (
                str(raw_merge_sha).casefold()
                if isinstance(raw_merge_sha, str)
                and valid_sha(str(raw_merge_sha).casefold())
                else None
            )
            self._finish(intent, success=True)
            return receipt(
                intent,
                MutationState.APPLIED,
                started=started,
                finished=_time(self.clock),
                current=current,
                merge_sha=merge_sha,
                message=str(result.get("message") or "merged"),
                preconditions=preconditions,
            )
        except GitHubHTTPError as exc:
            message = f"{type(exc).__name__}: {exc}"
            if mutation_dispatched and exc.definitive_mutation_rejection:
                self._finish(intent, success=False, error=message)
                return receipt(
                    intent,
                    MutationState.REJECTED,
                    started=started,
                    finished=_time(self.clock),
                    current=None,
                    message=message,
                )
            if mutation_dispatched:
                uncertain_message = (
                    "mutation outcome uncertain after merge request dispatch; "
                    "fresh repository reconciliation is required before any further mutation: "
                    + message
                )
                self._finish(
                    intent,
                    success=False,
                    error=uncertain_message,
                    uncertain=True,
                )
                return receipt(
                    intent,
                    MutationState.UNCERTAIN,
                    started=started,
                    finished=_time(self.clock),
                    current=None,
                    message=uncertain_message,
                )
            self._finish(intent, success=False, error=message)
            return receipt(
                intent,
                MutationState.FAILED,
                started=started,
                finished=_time(self.clock),
                current=None,
                message=message,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if mutation_dispatched:
                uncertain_message = (
                    "mutation outcome uncertain after merge request dispatch; "
                    "fresh repository reconciliation is required before any further mutation: "
                    + message
                )
                self._finish(
                    intent,
                    success=False,
                    error=uncertain_message,
                    uncertain=True,
                )
                return receipt(
                    intent,
                    MutationState.UNCERTAIN,
                    started=started,
                    finished=_time(self.clock),
                    current=None,
                    message=uncertain_message,
                )
            self._finish(intent, success=False, error=message)
            return receipt(
                intent,
                MutationState.FAILED,
                started=started,
                finished=_time(self.clock),
                current=None,
                message=message,
            )


def append_receipt_event(
    index: EventIndex,
    item: WorkItem,
    result: MutationReceipt,
    *,
    delivery_id: str | None,
) -> bool:
    event_type = f"runner_v2:mutation:{result.state.value}"
    return index.append(
        snapshot=item.snapshot.core,
        evaluation=item.evaluation,
        event_type=event_type,
        delivery_id=delivery_id,
        extra={
            "intent": asdict(result.intent),
            "state": result.state.value,
            "observed_head_sha": result.observed_head_sha,
            "observed_base_sha": result.observed_base_sha,
            "merge_sha": result.merge_sha,
            "message": result.message,
            "preconditions": (
                asdict(result.preconditions)
                if result.preconditions is not None
                else None
            ),
            "started_at": result.started_at,
            "finished_at": result.finished_at,
        },
    )


def mutation_retriable(result: MutationReceipt) -> bool:
    """Return whether a later *fresh reconciliation* may attempt again.

    This never means retry the same HTTP mutation.  It indicates whether another
    runner invocation may re-evaluate repository state and potentially produce a
    new idempotency key.
    """
    if result.state in {
        MutationState.APPLIED,
        MutationState.DUPLICATE,
        MutationState.UNCERTAIN,
    }:
        return False
    if result.state is MutationState.ABORTED:
        return True
    if result.state is MutationState.REJECTED:
        return True
    if result.state is MutationState.FAILED:
        return True
    return False


def transaction_diagnostics(
    result: MutationReceipt,
) -> Mapping[str, Any]:
    return {
        "pr": result.intent.pr_number,
        "state": result.state.value,
        "intent_key": result.intent.key,
        "expected_head_sha": result.intent.expected_head_sha,
        "expected_base_sha": result.intent.expected_base_sha,
        "observed_head_sha": result.observed_head_sha,
        "observed_base_sha": result.observed_base_sha,
        "merge_sha": result.merge_sha,
        "message": result.message,
        "failed_preconditions": (
            result.preconditions.failed()
            if result.preconditions is not None
            else ()
        ),
        "retriable_after_fresh_reconciliation": mutation_retriable(result),
    }


__all__ = [
    "BranchObservation",
    "MergeTransaction",
    "MutationError",
    "append_receipt_event",
    "branch_head",
    "branch_protected",
    "observe_branch",
    "compute_preconditions",
    "compute_transaction_preconditions",
    "mutation_retriable",
    "receipt",
    "transaction_diagnostics",
]
