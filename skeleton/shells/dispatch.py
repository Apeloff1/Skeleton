"""Dispatch coordinator that composes shell admission-time controls."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.admission_lease import AdmissionLease,AdmissionLeases
from skeleton.shells.cancellation import CancellationToken
from skeleton.shells.command_budget import CommandBudgets
from skeleton.shells.concurrency import ConcurrencyPermit,WeightedConcurrency
from skeleton.shells.deadlines import Deadline,DeadlineClock
from skeleton.shells.executor import ExecutionOutcome,ShellExecutor
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession
from skeleton.shells.shell_events import ShellEvents

@dataclass(frozen=True)
class DispatchResult:
    outcome:ExecutionOutcome
    context:ExecutionContext
    permit_id:int
    lease_id:str
    duration_ms:float

    @property
    def ok(self)->bool:
        return self.outcome.ok

class ShellDispatcher:
    """Explicit pre-dispatch checks around the existing ShellExecutor."""

    def __init__(
        self,
        executor:ShellExecutor,
        *,
        concurrency:WeightedConcurrency|None=None,
        budgets:CommandBudgets|None=None,
        events:ShellEvents|None=None,
        leases:AdmissionLeases|None=None,
        deadline_clock:DeadlineClock|None=None,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.executor=executor
        self.concurrency=concurrency or WeightedConcurrency(1,clock=clock)
        self.budgets=budgets or CommandBudgets(clock=clock)
        self.events=events or ShellEvents(clock=clock)
        self.leases=leases or AdmissionLeases(clock=clock)
        self.deadline_clock=deadline_clock or DeadlineClock(clock=clock)
        self._clock=clock

    def _effective_command(self,command:ShellCommand,deadline:Deadline|None)->ShellCommand:
        if deadline is None:
            return command
        requested=command.timeout or self.executor.runner.policy.default_timeout
        timeout=self.deadline_clock.clamp_timeout(deadline,requested)
        return ShellCommand(
            command.command,
            command.args,
            command.cwd,
            command.env,
            command.stdin,
            timeout,
            command.allowed_returncodes,
        )

    def dispatch(
        self,
        command:ShellCommand,
        *,
        context:ExecutionContext,
        cancellation:CancellationToken|None=None,
        deadline:Deadline|None=None,
        retry:RetryPolicy|None=None,
        session:ShellSession|None=None,
        weight:int=1,
        lease_key:str|None=None,
        lease_ttl_seconds:float=30.0,
    )->DispatchResult:
        if cancellation is not None:
            cancellation.require_active()
        effective=self._effective_command(command,deadline)
        decision=self.budgets.inspect(effective.command)
        if not decision.allowed:
            raise RuntimeError(decision.reason)

        key=lease_key or context.correlation_id
        lease=self.leases.acquire(
            key,
            principal=context.principal,
            command=effective.command,
            ttl_seconds=lease_ttl_seconds,
        )
        permit:ConcurrencyPermit|None=None
        started=self._clock()
        self.events.emit(
            "shell.dispatch.admitted",
            correlation_id=context.correlation_id,
            command=effective.command,
            data={"lease_id":lease.lease_id,"weight":weight},
        )
        try:
            permit=self.concurrency.acquire(weight,owner=context.principal)
            self.budgets.reserve_start(effective.command)
            self.events.emit(
                "shell.dispatch.started",
                correlation_id=context.correlation_id,
                command=effective.command,
                data={"permit_id":permit.permit_id,"lease_id":lease.lease_id,"weight":weight},
            )
            if cancellation is not None:
                cancellation.require_active()
            outcome=self.executor.execute(
                effective,
                retry=retry,
                session=session,
                correlation_id=context.correlation_id,
                circuit_key=effective.command,
            )
            duration_ms=max(0.0,(self._clock()-started)*1000)
            self.budgets.record_result(
                effective.command,
                ok=outcome.ok,
                runtime_ms=duration_ms,
                output_bytes=len(outcome.result.stdout)+len(outcome.result.stderr),
            )
            self.events.emit(
                "shell.dispatch.completed",
                correlation_id=context.correlation_id,
                command=effective.command,
                data={
                    "permit_id":permit.permit_id,
                    "lease_id":lease.lease_id,
                    "ok":outcome.ok,
                    "duration_ms":duration_ms,
                    "attempts":len(outcome.receipts),
                },
            )
            return DispatchResult(outcome,context,permit.permit_id,lease.lease_id,duration_ms)
        except BaseException as exc:
            duration_ms=max(0.0,(self._clock()-started)*1000)
            self.budgets.record_result(
                effective.command,
                ok=False,
                runtime_ms=duration_ms,
                output_bytes=0,
            )
            self.events.emit(
                "shell.dispatch.error",
                correlation_id=context.correlation_id,
                command=effective.command,
                data={
                    "lease_id":lease.lease_id,
                    "permit_id":None if permit is None else permit.permit_id,
                    "error_type":type(exc).__name__,
                    "duration_ms":duration_ms,
                },
            )
            raise
        finally:
            if permit is not None:
                self.concurrency.release(permit)
            self.leases.release(lease)
