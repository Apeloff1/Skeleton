"""Skeleton Contexts — The Context Fabric (with ResponseCycle)."""

from skeleton.contexts.workorder import WorkOrderEngine, WorkOrder, WorkOrderContext
from skeleton.contexts.backlog import BacklogContext, TensorCube, WorkChain, BacklogItem
from skeleton.contexts.planning import (
    PlanningContext,
    Plan,
    PlanStep,
    QueByPriority,
    QueuedItem,
    PROBABILITY_SYSTEMS,
)
from skeleton.contexts.oracle import OracleMatrix, OracleReading, FateString
from skeleton.contexts.syntax import ContextSyntaxFixer, SyntaxIssue
from skeleton.contexts.cycle import ResponseCycle, ConnectorExecutor, CycleReport
from typing import Any, Dict, Optional
from skeleton.kernel.events import EventBus


class ContextFabric:
    """The spider web: all context planes, connected and coordinated."""

    def __init__(self, bus: Optional[EventBus] = None, mag: Optional[Any] = None):
        self._bus = bus
        self.backlog = BacklogContext(bus=bus)
        self.workorders = WorkOrderEngine(mag=mag, bus=bus, backlog=self.backlog)
        self.planning = PlanningContext(bus=bus)
        self.queue = QueByPriority(bus=bus)
        self.oracle = OracleMatrix(
            queue=self.queue, planning=self.planning,
            backlog=self.backlog, workorders=self.workorders, bus=bus,
        )
        self.syntax = ContextSyntaxFixer(bus=bus)
        self._stats = {"cycles": 0}

    def connect_all(self) -> "ContextFabric":
        self.syntax.connect_all(
            workorder=self.workorders,
            backlog=self.backlog,
            planning=self.planning,
            queue=self.queue,
        )
        return self

    def distill(self, response_text: str, token_count: int) -> Dict[str, Any]:
        self._stats["cycles"] += 1
        context = self.workorders.distill(response_text, token_count)
        self.backlog.age_all()

        for order in context.active():
            if not any(i.payload is order for i in self.queue.items):
                self.queue.enqueue("workorder", order, record={
                    "action": order.action,
                    "priority": order.priority,
                    "appearances": 1,
                })

        issues = self.syntax.scan()

        return {
            "cycle": self._stats["cycles"],
            "orders_active": len(context.active()),
            "backlog": len(self.backlog.items),
            "queued": len(self.queue.items),
            "syntax_issues": len(issues),
        }

    def interject(self) -> Optional[str]:
        return self.workorders.interjected_summary()

    def guide(self) -> str:
        return self.oracle.guide()

    def start_idle_work(self) -> None:
        self.backlog.start_idle_miner()

    def stop_idle_work(self) -> None:
        self.backlog.stop_idle_miner()

    def summary(self) -> Dict[str, Any]:
        return {
            "cycles": self._stats["cycles"],
            "workorders": self.workorders.stats(),
            "backlog": self.backlog.summary(),
            "planning": self.planning.summary(),
            "queue": self.queue.summary(),
            "oracle": self.oracle.stats(),
            "syntax": self.syntax.stats(),
        }


__all__ = [
    "ContextFabric",
    "WorkOrderEngine",
    "WorkOrder",
    "WorkOrderContext",
    "BacklogContext",
    "TensorCube",
    "WorkChain",
    "BacklogItem",
    "PlanningContext",
    "Plan",
    "PlanStep",
    "QueByPriority",
    "QueuedItem",
    "PROBABILITY_SYSTEMS",
    "OracleMatrix",
    "OracleReading",
    "FateString",
    "ContextSyntaxFixer",
    "SyntaxIssue",
    "ResponseCycle",
    "ConnectorExecutor",
    "CycleReport",
]
