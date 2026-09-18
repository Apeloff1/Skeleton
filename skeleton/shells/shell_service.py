"""High-level shell-plane service composition without hidden background work."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.cancellation import CancellationRegistry
from skeleton.shells.command_budget import CommandBudgets
from skeleton.shells.concurrency import WeightedConcurrency
from skeleton.shells.dispatch import DispatchResult, ShellDispatcher
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan
from skeleton.shells.failure_ledger import ShellFailureKind, ShellFailureLedger
from skeleton.shells.incident import IncidentRegistry, IncidentSeverity
from skeleton.shells.plan_executor import PlanExecutionReport, ShellPlanExecutor
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.reconciler import ReconcileReport, ShellReconciler
from skeleton.shells.runner import ShellCommand
from skeleton.shells.service_state import ShellServicePhase, ShellServiceState
from skeleton.shells.shell_diagnostics import ShellDiagnostics, ShellDiagnosticsReport
from skeleton.shells.shell_events import ShellEvents
from skeleton.shells.shell_snapshot import ShellSnapshot, ShellSnapshotter
from skeleton.shells.status import status_snapshot


@dataclass(frozen=True)
class ShellServiceStatus:
    phase: ShellServicePhase
    diagnostics: dict[str, object]
    reconcile: dict[str, object]
    snapshot_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "diagnostics": dict(self.diagnostics),
            "reconcile": dict(self.reconcile),
            "snapshot_digest": self.snapshot_digest,
        }


class ShellService:
    """Composition facade around an existing ShellExecutor.

    Constructing this service starts no worker thread or process loop.
    """

    def __init__(
        self,
        executor,
        *,
        concurrency_capacity: int = 4,
        receipts: ReceiptChain | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.executor = executor
        self.clock = clock
        self.receipts = receipts or executor.receipt_chain or ReceiptChain()
        self.cancellations = CancellationRegistry(clock=clock)
        self.concurrency = WeightedConcurrency(concurrency_capacity, clock=clock)
        self.budgets = CommandBudgets(clock=clock)
        self.events = ShellEvents(clock=clock)
        self.failures = ShellFailureLedger(clock=clock)
        self.incidents = IncidentRegistry(clock=clock)
        self.dispatcher = ShellDispatcher(
            executor,
            concurrency=self.concurrency,
            budgets=self.budgets,
            events=self.events,
            clock=clock,
        )
        self.plans = ShellPlanExecutor(self.dispatcher, clock=clock)
        self.state = ShellServiceState(clock=clock)
        self.diagnostics = ShellDiagnostics(
            runner=executor.runner,
            receipts=self.receipts,
            cancellations=self.cancellations,
            concurrency=self.concurrency,
            budgets=self.budgets,
        )
        self.reconciler = ShellReconciler(
            receipts=self.receipts,
            events=self.events,
            failures=self.failures,
            concurrency=self.concurrency,
            budgets=self.budgets,
        )
        self.snapshotter = ShellSnapshotter(
            status_provider=lambda: status_snapshot(
                executor.runner,
                executor.telemetry,
                executor.circuits,
                self.receipts,
            ),
            diagnostics=self.diagnostics,
            cancellations=self.cancellations,
            concurrency=self.concurrency,
            budgets=self.budgets,
            receipts=self.receipts,
            clock=clock,
        )

    def start(self) -> None:
        if self.state.phase is ShellServicePhase.NEW:
            self.state.transition(ShellServicePhase.STARTING)
        if self.state.phase is ShellServicePhase.STARTING:
            report = self.diagnostics.inspect()
            if not report.ok:
                self.state.transition(ShellServicePhase.FAILED, reason="shell diagnostics failed")
                raise RuntimeError("shell service diagnostics failed")
            self.state.transition(ShellServicePhase.READY)

    def dispatch(self, command: ShellCommand, *, context: ExecutionContext, **kwargs) -> DispatchResult:
        if not self.state.ready():
            raise RuntimeError("shell service is not ready")
        try:
            return self.dispatcher.dispatch(command, context=context, **kwargs)
        except BaseException as exc:
            self.failures.record(
                command.command,
                ShellFailureKind.INTERNAL,
                correlation_id=context.correlation_id,
                detail=type(exc).__name__,
            )
            raise

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext,
        **kwargs,
    ) -> PlanExecutionReport:
        if not self.state.ready():
            raise RuntimeError("shell service is not ready")
        return self.plans.execute(plan, context=context, **kwargs)

    def diagnostics_report(self) -> ShellDiagnosticsReport:
        return self.diagnostics.inspect()

    def reconcile(self) -> ReconcileReport:
        return self.reconciler.reconcile()

    def snapshot(self) -> ShellSnapshot:
        return self.snapshotter.capture()

    def status(self) -> ShellServiceStatus:
        snapshot = self.snapshot()
        return ShellServiceStatus(
            self.state.phase,
            self.diagnostics_report().to_dict(),
            self.reconcile().to_dict(),
            snapshot.digest,
        )

    def open_incident(
        self,
        summary: str,
        *,
        severity: IncidentSeverity = IncidentSeverity.ERROR,
        correlation_id: str = "",
        command: str = "",
        evidence: dict[str, object] | None = None,
    ):
        return self.incidents.open(
            severity,
            summary,
            correlation_id=correlation_id,
            command=command,
            evidence=evidence,
        )
