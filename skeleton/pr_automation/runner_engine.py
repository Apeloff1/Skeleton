"""Runner-v2 orchestration engine.

The engine coordinates admission, target discovery, evidence collection,
scheduling, mutation transactions, EventIndex persistence, status publication,
and report construction.  It deliberately processes targets serially.  Reads
may be numerous, but mutation authorization is always based on a fresh
single-target snapshot and a single-shot transaction.

Legacy runner functions remain available from `runner.py`; this engine is the
new default execution path used by the upgraded CLI.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from .core import Decision, Evaluation, Mode
from .index import EventIndex
from .runner_contracts import (
    AdmissionDecision,
    MutationReceipt,
    MutationState,
    RunnerPolicy,
    RunnerReport,
    RunIdentity,
    Target,
    TargetResult,
    TargetSet,
    WorkItem,
    WorkState,
    bounded_text,
    utcnow,
)
from .runner_evidence import EvidenceCollector
from .runner_report import assert_report_invariants
from .runner_scheduler import (
    MutableBudget,
    QueueObservation,
    build_work_item,
    budget_allows_mutation,
    make_budget,
    observe_queue,
)
from .runner_targeting import TargetResolver
from .runner_transaction import MergeTransaction, append_receipt_event
from .runner_transport import BudgetedGitHubTransport, RunnerTransportError


GATE_CONTEXT = "PR Automation Gate"
_MUTATION_BUDGET_STATES = frozenset(
    {
        MutationState.APPLIED,
        MutationState.REJECTED,
        MutationState.UNCERTAIN,
    }
)


def _mutation_uses_budget(state: MutationState) -> bool:
    """Return whether a merge request was dispatched or may have been dispatched."""
    return state in _MUTATION_BUDGET_STATES


class RunnerEngineError(RuntimeError):
    pass


def _now(clock: Callable[[], datetime] | None = None) -> datetime:
    value = (clock or utcnow)()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _milliseconds(start: datetime, finish: datetime) -> int:
    return max(0, int((finish - start).total_seconds() * 1000))


def _status_state(evaluation: Evaluation) -> str:
    if evaluation.decision in {Decision.READY, Decision.MERGE}:
        return "success"
    if evaluation.decision is Decision.IGNORE:
        return "success"
    if any("failed" in reason for reason in evaluation.reasons):
        return "failure"
    return "pending"


def _status_description(evaluation: Evaluation) -> str:
    if evaluation.reasons:
        return bounded_text(evaluation.reasons[0], limit=140)
    return bounded_text(evaluation.decision.value, limit=140)


def publish_status(
    transport: BudgetedGitHubTransport,
    item: WorkItem,
    *,
    delivery_id: str,
    server_url: str = "https://github.com",
    force_state: str | None = None,
    description: str | None = None,
) -> None:
    repository = item.snapshot.core.repository
    sha = item.snapshot.core.head_sha
    target_url = (
        f"{server_url.rstrip('/')}/{repository}/actions/runs/"
        f"{delivery_id.split(':', 1)[0]}"
        if delivery_id and delivery_id.split(":", 1)[0].isdigit()
        else None
    )
    state = force_state or _status_state(item.evaluation)
    if state not in {"error", "failure", "pending", "success"}:
        raise ValueError(f"invalid commit status state: {state}")
    body: dict[str, Any] = {
        "state": state,
        "context": GATE_CONTEXT,
        "description": bounded_text(
            description or _status_description(item.evaluation),
            limit=140,
        ),
    }
    if target_url is not None:
        body["target_url"] = target_url
    transport.post(
        f"/repos/{repository}/statuses/{sha}",
        body,
        retry_safe=False,
    )


def append_evaluation_event(
    index: EventIndex,
    item: WorkItem,
    *,
    delivery_id: str,
    policy: RunnerPolicy,
) -> bool:
    return index.append(
        snapshot=item.snapshot.core,
        evaluation=item.evaluation,
        event_type="runner_v2:evaluation",
        delivery_id=delivery_id,
        extra={
            "runner_snapshot_fingerprint": item.snapshot.fingerprint(),
            "runner_policy_fingerprint": policy.fingerprint(),
            "score": item.score,
            "state": item.state.value,
            "reasons": item.reasons,
            "target": asdict(item.target),
            "observed_queue_depth": item.observed_queue_depth,
            "observed_rate_remaining": item.observed_rate_remaining,
        },
    )


def append_error_event(
    index: EventIndex,
    *,
    item: WorkItem | None,
    snapshot: Any | None,
    evaluation: Evaluation | None,
    delivery_id: str,
    error: str,
) -> bool:
    if item is not None:
        snapshot = item.snapshot.core
        evaluation = item.evaluation
    if snapshot is None or evaluation is None:
        return False
    return index.append(
        snapshot=snapshot,
        evaluation=evaluation,
        event_type="runner_v2:error",
        delivery_id=delivery_id,
        extra={"error": bounded_text(error, limit=2000)},
    )


def _queue_observation(
    transport: BudgetedGitHubTransport,
    repository: str,
    *,
    clock: Callable[[], datetime] | None = None,
) -> QueueObservation:
    queued: int | None
    try:
        queued = transport.queued_actions_count(repository)
    except RunnerTransportError:
        queued = None
    return observe_queue(
        queued_actions=queued,
        rate_remaining=transport.minimum_rate_remaining,
        now=_now(clock),
    )


def _failure_result(
    target: Target,
    *,
    started: datetime,
    finished: datetime,
    request_count: int,
    message: str,
) -> TargetResult:
    return TargetResult(
        number=target.number,
        state=WorkState.FAILED,
        decision=Decision.HOLD,
        reasons=("runner_error",),
        snapshot_fingerprint=None,
        mutations=(),
        request_count=max(0, request_count),
        duration_ms=_milliseconds(started, finished),
        error=bounded_text(message, limit=2000),
    )


def _deferred_result(
    item: WorkItem,
    *,
    started: datetime,
    finished: datetime,
    request_count: int,
    reasons: Sequence[str],
) -> TargetResult:
    return TargetResult(
        number=item.target.number,
        state=WorkState.DEFERRED,
        decision=item.evaluation.decision,
        reasons=tuple(dict.fromkeys((*item.reasons, *reasons))),
        snapshot_fingerprint=item.snapshot.fingerprint(),
        mutations=(),
        request_count=max(0, request_count),
        duration_ms=_milliseconds(started, finished),
    )


def _result_from_item(
    item: WorkItem,
    *,
    started: datetime,
    finished: datetime,
    request_count: int,
    receipts: Sequence[MutationReceipt] = (),
) -> TargetResult:
    state = item.state
    if any(receipt.state is MutationState.APPLIED for receipt in receipts):
        state = WorkState.MERGED
    elif any(
        receipt.state in {
            MutationState.FAILED,
            MutationState.REJECTED,
            MutationState.UNCERTAIN,
        }
        for receipt in receipts
    ):
        state = WorkState.FAILED
    elif any(receipt.state is MutationState.ABORTED for receipt in receipts):
        state = WorkState.DEFERRED

    error: str | None = None
    if state is WorkState.FAILED and receipts:
        error = "; ".join(
            receipt.message
            for receipt in receipts
            if receipt.state in {
                MutationState.FAILED,
                MutationState.REJECTED,
                MutationState.UNCERTAIN,
            }
        ) or None

    reasons = list(item.reasons)
    for receipt in receipts:
        if receipt.state is not MutationState.APPLIED:
            reasons.append(f"mutation:{receipt.state.value}:{receipt.message}")

    return TargetResult(
        number=item.target.number,
        state=state,
        decision=item.evaluation.decision,
        reasons=tuple(dict.fromkeys(reasons)),
        snapshot_fingerprint=item.snapshot.fingerprint(),
        mutations=tuple(receipts),
        request_count=max(0, request_count),
        duration_ms=_milliseconds(started, finished),
        error=bounded_text(error, limit=2000) if error else None,
    )


class RunnerEngine:
    def __init__(
        self,
        *,
        transport: BudgetedGitHubTransport,
        index: EventIndex,
        policy: RunnerPolicy,
        identity: RunIdentity,
        admission: AdmissionDecision,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.transport = transport
        self.index = index
        self.policy = policy
        self.identity = identity
        self.admission = admission
        self.clock = clock
        self.collector = EvidenceCollector(transport, policy)
        self.resolver = TargetResolver(transport, policy)
        self.transaction = MergeTransaction(
            transport,
            self.collector,
            index,
            policy,
            clock=clock,
        )
        self.budget = MutableBudget(
            make_budget(policy, started_at=_now(clock))
        )

    def _verify_index(self, number: int) -> None:
        if not self.index.verify_chain(
            self.identity.repository,
            number,
        ):
            raise RunnerEngineError(
                "EventIndex hash chain verification failed for "
                f"{self.identity.repository}#{number}"
            )

    def _collect_item(
        self,
        target: Target,
        observation: QueueObservation,
    ) -> WorkItem:
        self._verify_index(target.number)
        snapshot = self.collector.collect(
            self.identity.repository,
            target.number,
        )
        return build_work_item(
            target,
            snapshot,
            self.policy,
            observation,
            now=_now(self.clock),
        )

    def _maybe_publish(self, item: WorkItem, delivery_id: str) -> None:
        if not self.policy.publish_gate_status:
            return
        if item.evaluation.decision is Decision.IGNORE:
            return
        publish_status(
            self.transport,
            item,
            delivery_id=delivery_id,
        )

    def _process_target(
        self,
        target: Target,
        observation: QueueObservation,
    ) -> TargetResult:
        started = _now(self.clock)
        requests_before = self.transport.request_count
        delivery = f"{self.identity.delivery_id}:{target.number}"

        try:
            item = self._collect_item(target, observation)
            self.budget.consume_target()
            collection_requests = self.transport.request_count - requests_before
            if collection_requests > self.policy.limits.per_target_request_budget:
                finished = _now(self.clock)
                return _deferred_result(
                    item,
                    started=started,
                    finished=finished,
                    request_count=collection_requests,
                    reasons=(
                        "per_target_request_budget_exceeded:"
                        f"{collection_requests}:"
                        f"{self.policy.limits.per_target_request_budget}",
                    ),
                )
            append_evaluation_event(
                self.index,
                item,
                delivery_id=delivery,
                policy=self.policy,
            )
            self._maybe_publish(item, delivery)

            receipts: list[MutationReceipt] = []
            if (
                self.admission.mutation_authorized
                and self.policy.mode is Mode.APPLY
                and item.state is WorkState.READY
                and item.evaluation.decision is Decision.MERGE
                and item.evaluation.actions
            ):
                fresh_observation = _queue_observation(
                    self.transport,
                    self.identity.repository,
                    clock=self.clock,
                )
                allowed = budget_allows_mutation(
                    self.budget.value,
                    fresh_observation,
                    self.policy,
                    now=_now(self.clock),
                )
                if not allowed.allowed:
                    if self.policy.publish_gate_status:
                        publish_status(
                            self.transport,
                            item,
                            delivery_id=delivery,
                            force_state="pending",
                            description=allowed.reasons[0]
                            if allowed.reasons
                            else "mutation deferred",
                        )
                    finished = _now(self.clock)
                    return _deferred_result(
                        item,
                        started=started,
                        finished=finished,
                        request_count=self.transport.request_count - requests_before,
                        reasons=allowed.reasons,
                    )

                result = self.transaction.apply(item)
                receipts.append(result)
                append_receipt_event(
                    self.index,
                    item,
                    result,
                    delivery_id=f"{delivery}:mutation",
                )
                if _mutation_uses_budget(result.state):
                    self.budget.consume_mutation()
                if (
                    self.policy.publish_gate_status
                    and result.state
                    not in {MutationState.APPLIED, MutationState.DUPLICATE}
                ):
                    publish_status(
                        self.transport,
                        item,
                        delivery_id=delivery,
                        force_state=(
                            "error"
                            if result.state in {
                                MutationState.FAILED,
                                MutationState.UNCERTAIN,
                            }
                            else "pending"
                        ),
                        description=(
                            f"mutation {result.state.value}: {result.message}"
                        ),
                    )

            finished = _now(self.clock)
            return _result_from_item(
                item,
                started=started,
                finished=finished,
                request_count=self.transport.request_count - requests_before,
                receipts=receipts,
            )
        except Exception as exc:
            finished = _now(self.clock)
            return _failure_result(
                target,
                started=started,
                finished=finished,
                request_count=self.transport.request_count - requests_before,
                message=f"{type(exc).__name__}: {exc}",
            )

    def run(self) -> RunnerReport:
        started = _now(self.clock)

        # A dropped event is not allowed to spend repository-read budget.  It
        # emits a diagnostic report with an intentionally empty target set so
        # malformed/untrusted workflow identity cannot be turned into a broad
        # repository scan.
        if self.admission.dropped:
            targets = TargetSet(
                repository=self.identity.repository,
                targets=(),
                complete=True,
                reason="admission_drop",
                requests_used=0,
            )
            finished = _now(self.clock)
            report = RunnerReport(
                identity=self.identity,
                admission=self.admission,
                policy_fingerprint=self.policy.fingerprint(),
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                targets=targets,
                results=(),
                transport=self.transport.summary(),
                mutations_attempted=0,
                mutations_applied=0,
                failures=0,
                deferred=0,
                final_queue_depth=None,
                final_rate_remaining=self.transport.minimum_rate_remaining,
            )
            assert_report_invariants(report)
            return report

        # Target discovery is the first repository-read phase for admitted
        # runs. Resolve once, preserve its completeness bit in the report, and
        # schedule only identities admitted by the bounded resolver.
        targets = self.resolver.resolve(self.identity)

        initial_observation = _queue_observation(
            self.transport,
            self.identity.repository,
            clock=self.clock,
        )
        results: list[TargetResult] = []

        # Resolve schedule lazily.  Evidence collection itself consumes request
        # budget and the repository may evolve while earlier targets run.  We
        # therefore schedule target identities first, then collect each target
        # immediately before evaluation.
        ordered_targets = sorted(
            targets.targets,
            key=lambda target: (
                {
                    "interactive": 0,
                    "completion": 1,
                    "recovery": 2,
                    "sweep": 3,
                }[target.priority.value],
                target.number,
            ),
        )

        for target in ordered_targets:
            if self.budget.value.remaining_targets() <= 0:
                break
            result = self._process_target(
                target,
                initial_observation,
            )
            results.append(result)

            if self.transport.request_count >= self.policy.limits.max_requests:
                break
            if self.budget.value.remaining_mutations() <= 0:
                # Continue evaluating remaining targets in observe mode only if
                # request/deadline budgets permit; they remain useful status
                # evidence, but no further merge transaction can start.
                pass

        processed = {result.number for result in results}
        for target in ordered_targets:
            if target.number in processed:
                continue
            now = _now(self.clock)
            results.append(
                TargetResult(
                    number=target.number,
                    state=WorkState.DEFERRED,
                    decision=Decision.HOLD,
                    reasons=("runner_budget_exhausted",),
                    snapshot_fingerprint=None,
                    mutations=(),
                    request_count=0,
                    duration_ms=0,
                )
            )

        try:
            final_queue = self.transport.queued_actions_count(
                self.identity.repository
            )
        except RunnerTransportError:
            final_queue = None

        finished = _now(self.clock)
        attempts = sum(
            len(result.mutations)
            for result in results
        )
        applied = sum(
            receipt.state is MutationState.APPLIED
            for result in results
            for receipt in result.mutations
        )
        failures = sum(
            result.state is WorkState.FAILED
            or result.error is not None
            for result in results
        )
        deferred = sum(
            result.state is WorkState.DEFERRED
            for result in results
        )

        report = RunnerReport(
            identity=self.identity,
            admission=self.admission,
            policy_fingerprint=self.policy.fingerprint(),
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            targets=targets,
            results=tuple(results),
            transport=self.transport.summary(),
            mutations_attempted=attempts,
            mutations_applied=applied,
            failures=failures,
            deferred=deferred,
            final_queue_depth=final_queue,
            final_rate_remaining=self.transport.minimum_rate_remaining,
        )
        assert_report_invariants(report)
        return report


def run_engine(
    *,
    transport: BudgetedGitHubTransport,
    index: EventIndex,
    policy: RunnerPolicy,
    identity: RunIdentity,
    admission: AdmissionDecision,
    clock: Callable[[], datetime] | None = None,
) -> RunnerReport:
    return RunnerEngine(
        transport=transport,
        index=index,
        policy=policy,
        identity=identity,
        admission=admission,
        clock=clock,
    ).run()


def report_has_merge(report: RunnerReport, pr_number: int) -> bool:
    return any(
        receipt.state is MutationState.APPLIED
        for result in report.results
        if result.number == pr_number
        for receipt in result.mutations
    )


def report_result(
    report: RunnerReport,
    pr_number: int,
) -> TargetResult | None:
    return next(
        (
            result
            for result in report.results
            if result.number == pr_number
        ),
        None,
    )


def successful_target_numbers(
    report: RunnerReport,
) -> tuple[int, ...]:
    return tuple(
        result.number
        for result in report.results
        if result.state in {
            WorkState.READY,
            WorkState.MERGED,
            WorkState.IGNORED,
            WorkState.HELD,
        }
        and result.error is None
    )


__all__ = [
    "GATE_CONTEXT",
    "RunnerEngine",
    "RunnerEngineError",
    "append_error_event",
    "append_evaluation_event",
    "publish_status",
    "report_has_merge",
    "report_result",
    "run_engine",
    "successful_target_numbers",
]
