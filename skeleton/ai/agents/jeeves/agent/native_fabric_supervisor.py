"""Operational Jeeves native batch supervisor: admitted work -> durable model.

Connects the host-owned control fabric to the already authoritative
NativeBatchConveyor, which delegates actual generation to the canonical
SupervisedAI/ExecutionSpine. The additional scheduler, budget and event
journal provide *in-process* admission and conservation checks only.
External model effects remain in the protected native SQLite/WAL database.

Execution is deliberately serial on a laptop. Each model request is
principal+model bound, reserved before generation, committed only after
the canonical receipt was replay-verified, and quarantined after any
ambiguous result. The workload cannot escalate to tools, network services,
hosted providers or generated shell commands. A process crash discards the
in-memory scheduler; only the canonical native SQLite receipt/unknown-intent
fences are restart proof.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import math
import time
from typing import Any, Callable, Sequence

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from .native_batch_runtime import (
    NativeBatchConveyor, NativeBatchHold, NativeBatchPolicy,
    NativeBatchTask, NativeBatchReceipt, batch_identity,
    preflight_batch_tasks,
)
from skeleton.jeeves.native_fabric.budgets import (
    BudgetLedger, ResourceBudget,
)
from skeleton.jeeves.native_fabric.contracts import (
    ContractHold, Scope, exact_integer,
)
from skeleton.jeeves.native_fabric.events import (
    EventJournal,
)
from skeleton.jeeves.native_fabric.traffic import (
    FairTrafficQueue, TrafficRequest,
)


class NativeFabricHold(NativeBatchHold):
    """The integrated native custody, budget or source identity is unresolved."""


@dataclass(frozen=True, slots=True)
class FabricJob:
    task: NativeBatchTask
    cohort: str = "operator"
    priority: int = 0

    def __post_init__(self):
        if not isinstance(self.task, NativeBatchTask):
            raise NativeFabricHold("typed operator native batch task required")
        from skeleton.jeeves.native_fabric.contracts import identifier
        identifier(self.cohort, "cohort")
        exact_integer(self.priority, maximum=1000)


@dataclass(frozen=True, slots=True)
class FabricRunPolicy:
    maximum_jobs: int = 64
    maximum_active_native: int = 1
    maximum_pending: int = 64
    maximum_per_scope: int = 1
    maximum_cohorts: int = 32
    maximum_events: int = 4096
    maximum_wall_seconds: float = 1800.0
    maximum_single_job_ms: int = 300000
    maximum_total_reserved_output_tokens: int = 65536
    maximum_input_bytes: int = 262144

    def __post_init__(self):
        for name, high in (
            ("maximum_jobs", 1000),
            ("maximum_active_native", 8),
            ("maximum_pending", 10000),
            ("maximum_per_scope", 8),
            ("maximum_cohorts", 128),
            ("maximum_events", 100000),
            ("maximum_single_job_ms", 600000),
            ("maximum_total_reserved_output_tokens", 8192000),
            ("maximum_input_bytes", 1048576),
        ):
            exact_integer(getattr(self, name), minimum=1, maximum=high)
        if (type(self.maximum_wall_seconds) not in (float, int)
            or not math.isfinite(self.maximum_wall_seconds)
            or not 0 < self.maximum_wall_seconds <= 86400):
            raise NativeFabricHold("invalid bounded native fabric wall time")
        if self.maximum_pending < self.maximum_jobs:
            raise NativeFabricHold("all authorized native jobs must fit admission")
        if self.maximum_per_scope > self.maximum_active_native:
            raise NativeFabricHold("per-scope admission exceeds global native slots")
        if self.maximum_events < 3 * self.maximum_jobs:
            raise NativeFabricHold("event window cannot retain run provenance")

    def native_batch_policy(self) -> NativeBatchPolicy:
        return NativeBatchPolicy(
            maximum_jobs=self.maximum_jobs,
            maximum_prompt_bytes=self.maximum_input_bytes,
            maximum_reserved_output_tokens=self.maximum_total_reserved_output_tokens,
            maximum_wall_seconds=self.maximum_wall_seconds,
            maximum_single_job_ms=self.maximum_single_job_ms,
            abort_on_failed_exact_predicate=True,
        )


@dataclass(frozen=True, slots=True)
class FabricJobReceipt:
    task_id: str
    batch_receipt: NativeBatchReceipt
    budget_ticket_sha256: str
    traffic_receipt_sha256: str
    event_entry_sha256: str

    def __post_init__(self):
        if self.task_id != self.batch_receipt.task_id:
            raise NativeFabricHold("host job and native receipt refer to different tasks")

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_fabric_job.v1",
            "task_id": self.task_id,
            "native": self.batch_receipt.to_public_record(),
            "budget_ticket_sha256": self.budget_ticket_sha256,
            "traffic_receipt_sha256": self.traffic_receipt_sha256,
            "event_entry_sha256": self.event_entry_sha256,
            "source_only_auxiliary_admission": True,
            "release_certified": False,
        }


@dataclass(frozen=True, slots=True)
class FabricRunResult:
    batch_id: str
    batch_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    ordered_results: tuple[FabricJobReceipt, ...]
    auxiliary_event_root: str
    auxiliary_event_count: int
    auxiliary_budget_snapshot: dict[str, object]
    auxiliary_traffic_snapshot: dict[str, object]

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_fabric_run.v1",
            "batch_id": self.batch_id,
            "batch_sha256": self.batch_sha256,
            "model_sha256": self.model_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "ordered_results": [item.to_record() for item in self.ordered_results],
            "committed": sum(not x.batch_receipt.replayed for x in self.ordered_results),
            "replayed": sum(x.batch_receipt.replayed for x in self.ordered_results),
            "auxiliary_event_root": self.auxiliary_event_root,
            "auxiliary_event_count": self.auxiliary_event_count,
            "auxiliary_budget_snapshot": self.auxiliary_budget_snapshot,
            "auxiliary_traffic_snapshot": self.auxiliary_traffic_snapshot,
            "native_sqlite_is_only_effect_authority": True,
            "auxiliary_journals_restart_safe": False,
            "physical_gguf_qualified": False,
            "device_pressure_qualified": False,
            "release_certified": False,
        }


class NativeFabricSupervisor:
    """End-to-end host admission around a real native batch conveyor.

    The complete planned batch is preflighted against the *actual* installed
    worker token and byte ceilings before any inference. The fair queue
    may reorder independent tasks according to explicitly authorized cohort
    and priority; it never changes a task's stable native request identity.
    """

    def __init__(
        self, worker: Any, *,
        approved: bool,
        policy: FabricRunPolicy | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if approved is not True:
            raise NativeFabricHold("explicit operator approval required before native effects")
        self.worker = worker
        self.identity = ActiveModel.from_supervisor(worker)
        self.policy = policy or FabricRunPolicy()
        if not isinstance(self.policy, FabricRunPolicy):
            raise NativeFabricHold("typed native fabric policy required")
        if not all(callable(x) for x in (monotonic, monotonic_ns, clock_ns)):
            raise NativeFabricHold("monotonic and observation clocks required")
        if self.policy.maximum_active_native != 1:
            # This first laptop implementation is intentionally serial.
            # A multi-worker variant needs separately qualified device
            # quotas, process isolation and SQLite pending-effect leases.
            raise NativeFabricHold("one serialized native execution lane supported")
        self._monotonic = monotonic
        self._monotonic_ns = monotonic_ns
        self._clock_ns = clock_ns
        self._used = False
        self._scope = Scope(
            tenant=self.identity.tenant,
            subject=self.identity.subject,
            model_sha256=self.identity.model_sha256,
            tokenizer_sha256=self.identity.tokenizer_sha256,
        )
        self.native = NativeBatchConveyor(
            worker, approved=True,
            policy=self.policy.native_batch_policy(),
            monotonic=monotonic,
        )

    def _reservations(
        self, tasks: Sequence[FabricJob],
    ) -> tuple[BudgetLedger, FairTrafficQueue, EventJournal]:
        limits = self.worker.spine.limits
        count = len(tasks)
        requested = ResourceBudget(
            inference_calls=count,
            prompt_tokens=count * limits.context_tokens,
            output_tokens=count * limits.max_output_tokens,
            tool_calls=0,
            bytes_read=sum(len(x.task.prompt.encode("utf-8", "strict")) for x in tasks),
            bytes_written=count * limits.response_bytes,
            wall_ms=count * self.policy.maximum_single_job_ms,
        )
        ledger = BudgetLedger(
            requested, clock=self._monotonic,
            maximum_tickets=self.policy.maximum_jobs,
        )
        traffic = FairTrafficQueue(
            maximum_pending=self.policy.maximum_pending,
            maximum_active=1,
            maximum_per_scope=1,
            maximum_cohorts=self.policy.maximum_cohorts,
            clock_ns=self._monotonic_ns,
        )
        journal = EventJournal(
            maximum_events=self.policy.maximum_events,
            clock_ns=self._clock_ns,
        )
        return ledger, traffic, journal

    def _before_model(
        self, batch_id: str, tasks: Sequence[FabricJob],
    ) -> tuple[tuple[FabricJob, ...], str]:
        from skeleton.jeeves.native_fabric.contracts import identifier
        identifier(batch_id, "batch")
        if type(tasks) not in (tuple, list) or not 1 <= len(tasks) <= self.policy.maximum_jobs:
            raise NativeFabricHold("bounded approved fabric batch required")
        if any(not isinstance(x, FabricJob) for x in tasks):
            raise NativeFabricHold("host batch job type invalid")
        tasks = tuple(tasks)
        ids = [x.task.task_id for x in tasks]
        if len(set(ids)) != len(ids):
            raise NativeFabricHold("duplicate operator task identity")
        if len({x.cohort for x in tasks}) > self.policy.maximum_cohorts:
            raise NativeFabricHold("too many native execution cohorts")
        self.native._check(batch_id, tuple(x.task for x in tasks))
        preflight_batch_tasks(
            batch_id, tuple(x.task for x in tasks),
            self.native.policy,
            configured_output_tokens=self.worker.spine.limits.max_output_tokens,
        )
        if ActiveModel.from_supervisor(self.worker) != self.identity:
            raise NativeFabricHold("source-verified active native model changed")
        return tasks, batch_identity(
            batch_id, tuple(x.task for x in tasks),
            tenant=self.identity.tenant,
            subject=self.identity.subject,
            model_sha256=self.identity.model_sha256,
            tokenizer_sha256=self.identity.tokenizer_sha256,
        )

    def run(
        self, batch_id: str,
        tasks: Sequence[FabricJob],
    ) -> FabricRunResult:
        if self._used:
            # Cross-call resource accounting in the same supervisor instance
            # requires a durable epoch policy, not an in-memory reset.
            raise NativeFabricHold("one authorized batch per supervisor epoch")
        jobs, batch_sha = self._before_model(batch_id, tasks)
        self._used = True
        started = self._monotonic()
        ledger, traffic, journal = self._reservations(jobs)
        index: dict[str, FabricJob] = {}
        for item in jobs:
            session, request = self.native._session_key(batch_id, item.task.task_id)
            if request in index:
                raise NativeFabricHold("native request digest collision")
            index[request] = item
            now = self._monotonic_ns()
            traffic.submit(TrafficRequest(
                request_id=request, scope_sha256=self._scope.binding,
                prompt_sha256=item.task.prompt_sha256,
                session_id=session,
                output_token_ceiling=self.worker.spine.limits.max_output_tokens,
                priority=item.priority,
                created_ns=now,
                deadline_ns=now + self.policy.maximum_single_job_ms * 1000000,
                cohort=item.cohort,
                tool_actions_allowed=False,
            ))
        result: list[FabricJobReceipt] = []
        for _ in jobs:
            if self._monotonic() - started >= self.policy.maximum_wall_seconds:
                raise NativeFabricHold("operator native fabric wall time exhausted")
            ticket = traffic.claim_next()
            if ticket is None:
                raise NativeFabricHold("native traffic cannot safely admit another job")
            task = index[ticket.request.request_id].task
            reservation = ResourceBudget(
                inference_calls=1,
                prompt_tokens=self.worker.spine.limits.context_tokens,
                output_tokens=self.worker.spine.limits.max_output_tokens,
                tool_calls=0,
                bytes_read=len(task.prompt.encode("utf-8", "strict")),
                bytes_written=self.worker.spine.limits.response_bytes,
                wall_ms=self.policy.maximum_single_job_ms,
            )
            reserve = ledger.reserve(
                ticket.request.request_id,
                self._scope.binding,
                reservation,
                deadline_ms=self.policy.maximum_single_job_ms,
            )
            journal.append(
                self._scope.binding, "native_request_reserved",
                payload={
                    "batch_sha256": batch_sha,
                    "request_binding": ticket.request.binding,
                    "reservation_sha256": reserve.checksum,
                },
            )
            try:
                # Exactly one production batch task, stable native request ID.
                # Previous SQLite commitment is replayed, unknown pending
                # effects remain held at the canonical execution spine.
                native = self.native.run(batch_id, (task,))
                if len(native.receipts) != 1:
                    raise NativeFabricHold("no unique authoritative native result")
                receipt = native.receipts[0]
                if (receipt.task_id != task.task_id
                    or receipt.request_id != ticket.request.request_id
                    or receipt.session_id != ticket.request.session_id
                    or receipt.prompt_sha256 != ticket.request.prompt_sha256
                    or receipt.model_sha256 != self.identity.model_sha256
                    or receipt.tokenizer_sha256 != self.identity.tokenizer_sha256):
                    raise NativeFabricHold("native response receipt differs from admitted work")
                # No native call is consumed on SQLite replay. The prompt
                # was still read, and receipt bytes still entered process RAM.
                used = ResourceBudget(
                    inference_calls=0 if receipt.replayed else 1,
                    prompt_tokens=0 if receipt.replayed else receipt.prompt_tokens,
                    output_tokens=0 if receipt.replayed else receipt.generated_tokens,
                    tool_calls=0,
                    bytes_read=len(task.prompt.encode("utf-8", "strict")),
                    bytes_written=receipt.answer_bytes,
                    wall_ms=receipt.duration_ms,
                )
                reconciled = ledger.reconcile(
                    ticket.request.request_id, used,
                    authoritative_commit=True,
                )
                settled = traffic.commit(
                    ticket.request.request_id,
                    authoritative_receipt_sha256=receipt.output_sha256,
                )
                event = journal.append(
                    self._scope.binding, "native_request_committed",
                    payload={
                        "batch_sha256": batch_sha,
                        "request_binding": ticket.request.binding,
                        "model_output_sha256": receipt.output_sha256,
                        "replayed": receipt.replayed,
                        "budget_sha256": reconciled.checksum,
                    },
                )
                result.append(FabricJobReceipt(
                    task_id=task.task_id,
                    batch_receipt=receipt,
                    budget_ticket_sha256=reconciled.checksum,
                    traffic_receipt_sha256=settled.committed_receipt_sha256,
                    event_entry_sha256=event.event_sha256,
                ))
            except BaseException:
                # Native effects may already have happened; in-process
                # reservation remains held and no speculative refund occurs.
                if traffic.inspect(ticket.request.request_id).state == "claimed":
                    traffic.hold(ticket.request.request_id)
                if any(
                    x.reservation_id == ticket.request.request_id
                    and x.state == "reserved"
                    for x in ledger.inventory
                ):
                    ledger.quarantine(ticket.request.request_id)
                journal.append(
                    self._scope.binding, "native_request_held",
                    payload={
                        "batch_sha256": batch_sha,
                        "request_binding": ticket.request.binding,
                        "native_effect_unknown": True,
                    },
                )
                raise
        ledger.assert_consistent()
        journal.verify()
        return FabricRunResult(
            batch_id=batch_id,
            batch_sha256=batch_sha,
            model_sha256=self.identity.model_sha256,
            tokenizer_sha256=self.identity.tokenizer_sha256,
            ordered_results=tuple(result),
            auxiliary_event_root=journal.tip[1],
            auxiliary_event_count=journal.tip[0],
            auxiliary_budget_snapshot=ledger.public_snapshot(),
            auxiliary_traffic_snapshot=traffic.snapshot(),
        )


__all__ = [
    "NativeFabricHold", "FabricJob", "FabricRunPolicy",
    "FabricJobReceipt", "FabricRunResult", "NativeFabricSupervisor",
]
