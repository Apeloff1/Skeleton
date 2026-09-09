"""
Skeleton Contexts — Response Cycle

Drives the ContextFabric through the live conversation loop:

    user turn → provider reply → distill (work orders parsed)
    → between turns: dequeue and execute orders via connector handlers
    → interjected summary prepended to the next reply (positive framing)
    → oracle narration attached when a golden path shifts

This is the piece that makes the fabric conversational rather than
infrastructural: work happens between responses, and the user sees
the surprise payload.

Provides:
- ResponseCycle: per-turn orchestrator bound to a ContextFabric
- ConnectorExecutor: pluggable executor registry (simulated by default)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class CycleReport:
    """What happened between two turns."""
    cycle: int
    orders_parsed: int = 0
    orders_executed: int = 0
    orders_failed: int = 0
    interjection: Optional[str] = None
    oracle_shift: Optional[str] = None
    backlog_sealed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle": self.cycle,
            "orders_parsed": self.orders_parsed,
            "orders_executed": self.orders_executed,
            "orders_failed": self.orders_failed,
            "interjection": self.interjection,
            "oracle_shift": self.oracle_shift,
            "backlog_sealed": self.backlog_sealed,
        }


class ConnectorExecutor:
    """Executes work orders against connector handlers.

    Handlers register per connector (`github.push`, `web.search`, ...).
    Without a handler, execution is simulated: the order succeeds with
    a synthetic result, so the loop is fully testable offline. Real
    deployments register live connector functions.
    """

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._handlers: Dict[str, Callable[[Any], Any]] = {}
        self._stats = {"executed": 0, "simulated": 0, "failed": 0}

    def register(self, connector: str, handler: Callable[[Any], Any]) -> None:
        self._handlers[connector] = handler

    def execute(self, order: Any) -> Dict[str, Any]:
        handler = self._handlers.get(order.connector)
        try:
            if handler is not None:
                result = handler(order)
                self._stats["executed"] += 1
            else:
                result = {"simulated": True, "connector": order.connector, "action": order.action,
                          "context": order.payload.get("context", "")[:80]}
                self._stats["simulated"] += 1
            return {"ok": True, "result": result}
        except Exception as e:
            self._stats["failed"] += 1
            return {"ok": False, "error": str(e)}

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)


class ResponseCycle:
    """Per-turn orchestrator: distill → execute → interject → guide."""

    def __init__(self, fabric: Any, executor: Optional[ConnectorExecutor] = None,
                 bus: Optional[EventBus] = None, max_executions_per_turn: int = 3):
        self._fabric = fabric
        self.executor = executor or ConnectorExecutor(bus=bus)
        self._bus = bus
        self.max_executions = max_executions_per_turn
        self._last_golden: Optional[str] = None
        self._pending_interjection: Optional[str] = None
        self._stats = {"turns": 0}

    def after_reply(self, response_text: str, token_count: int) -> CycleReport:
        """Run the full between-turns cycle after a reply is produced."""
        self._stats["turns"] += 1
        report = CycleReport(cycle=self._stats["turns"])

        # 1. Distill the reply: parse external workload into the fabric
        summary = self._fabric.distill(response_text, token_count)
        report.orders_parsed = summary["orders_active"]

        # 2. Execute queued orders (bounded per turn — the rest stay queued)
        for _ in range(self.max_executions):
            item = self._fabric.queue.dequeue()
            if item is None:
                break
            if item.kind != "workorder" or item.payload is None:
                continue
            order = item.payload
            order.status = "executing"
            outcome = self.executor.execute(order)
            if outcome["ok"]:
                self._fabric.workorders.mark(order.order_id, "done", result=outcome["result"])
                report.orders_executed += 1
            else:
                self._fabric.workorders.mark(order.order_id, "failed")
                self._fabric.backlog.defer(order, kind="failed_order")
                report.orders_failed += 1

        # 3. Backlog cube for the idle miner
        if self._fabric.backlog.items:
            self._fabric.backlog.build_cube()

        # 4. Interjection for the NEXT reply (positive framing)
        self._pending_interjection = self._fabric.interject()
        report.interjection = self._pending_interjection

        # 5. Oracle: note when the golden path shifts
        reading = self._fabric.oracle.read()
        golden_id = reading.golden_path.string_id if reading.golden_path else None
        if golden_id and golden_id != self._last_golden:
            self._last_golden = golden_id
            report.oracle_shift = reading.narrate()

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="contexts.cycle.completed",
                payload=report.to_dict(),
                correlation_id=f"cycle_{report.cycle}",
            ))
        return report

    def before_reply(self) -> Optional[str]:
        """Consume the pending interjection (prepended to the next reply)."""
        out = self._pending_interjection
        self._pending_interjection = None
        return out

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "executor": self.executor.stats()}
