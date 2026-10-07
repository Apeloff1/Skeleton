"""Plan-level execution backend abstraction for AI orchestration.

Backends receive an already compiled ExecutionPlan. They never receive raw model
text and cannot widen the reviewed plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan
from skeleton.shells.plan_executor import PlanExecutionReport
from skeleton.shells.shell_service import ShellService


@runtime_checkable
class AIPlanExecutionBackend(Protocol):
    @property
    def backend_id(self) -> str: ...

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext,
    ) -> PlanExecutionReport: ...

    def receipt_root(self) -> str: ...


@dataclass
class ShellServiceExecutionBackend:
    shell_service: ShellService
    backend_id: str = "shell-service-host"

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext,
    ) -> PlanExecutionReport:
        return self.shell_service.execute_plan(plan, context=context)

    def receipt_root(self) -> str:
        return self.shell_service.receipts.root_hash()
