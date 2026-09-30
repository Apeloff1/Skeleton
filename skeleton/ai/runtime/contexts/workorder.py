"""
Skeleton Contexts — Work Order Context

The systematic workhorse of the context fabric. It parses ONLY the
workload destined for external tools (connector-bound work), distills
it from max-token responses into compact work orders, and routes it
between user-facing responses that need no connectors.

Pipeline per response cycle:

    raw response (max token) → parse external workload → WorkOrder(s)
    → MAG enhancement (episodic context enriches each order)
    → distill into WorkOrderContext (fixed-size, like other contexts)
    → hand to connectors for execution between responses
    → interjected summary back into the conversation (positive framing)

The user-facing effect: responses at max token yield a surprise
payload of executed work, setting up a multi-response back-and-forth
with interjected progress summaries.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


# Work signals: a response contains external workload when it names
# a tool action. Only these get parsed into orders — everything else
# is conversational and flows straight back to the user.
EXTERNAL_SIGNALS: Dict[str, str] = {
    "push": "github.push",
    "commit": "github.push",
    "create repo": "github.create_repo",
    "pull request": "github.pull_request",
    "search the web": "web.search",
    "look up": "web.search",
    "read page": "web.extract",
    "generate image": "image.create",
    "edit image": "image.edit",
    "build pdf": "doc.pdf",
    "build docx": "doc.docx",
    "build xlsx": "doc.xlsx",
    "build pptx": "doc.pptx",
    "build chart": "doc.chart",
    "send email": "mail.send",
    "schedule": "calendar.create",
}

CONTEXT_SIZE = 32  # same fixed size as the other context planes


@dataclass
class WorkOrder:
    """A single parsed unit of external-tool work."""
    order_id: str
    connector: str
    action: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: float = 1.0
    status: str = "queued"  # queued | assigned | executing | done | failed
    created_at: float = field(default_factory=time.time)
    mag_context: List[str] = field(default_factory=list)  # episodic enrichment
    result: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "connector": self.connector,
            "action": self.action,
            "priority": round(self.priority, 3),
            "status": self.status,
            "mag_context": self.mag_context[:3],
        }


@dataclass
class WorkOrderContext:
    """Fixed-size context plane holding the active work orders.

    Sized exactly like the other context planes (CONTEXT_SIZE slots).
    Orders beyond capacity are spilled to the BacklogContext — never
    dropped silently.
    """
    slots: List[WorkOrder] = field(default_factory=list)
    distilled_from_tokens: int = 0
    cycle: int = 0

    def add(self, order: WorkOrder) -> Optional[WorkOrder]:
        """Add an order; returns the spilled order when full."""
        if len(self.slots) >= CONTEXT_SIZE:
            return order
        self.slots.append(order)
        return None

    def active(self) -> List[WorkOrder]:
        return [o for o in self.slots if o.status in ("queued", "assigned", "executing")]

    def compact(self) -> None:
        """Drop completed orders, keep the plane at working size."""
        self.slots = [o for o in self.slots if o.status != "done"]

    def summary(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for o in self.slots:
            by_status[o.status] = by_status.get(o.status, 0) + 1
        return {
            "slots_used": len(self.slots),
            "capacity": CONTEXT_SIZE,
            "by_status": by_status,
            "cycle": self.cycle,
            "distilled_from_tokens": self.distilled_from_tokens,
        }


class WorkOrderEngine:
    """Parses, enriches, distills, and tracks external-tool work orders."""

    def __init__(self, mag: Optional[Any] = None, bus: Optional[EventBus] = None,
                 backlog: Optional[Any] = None):
        self._mag = mag            # MAGStore for episodic enhancement
        self._bus = bus
        self._backlog = backlog    # BacklogContext for spillover
        self.context = WorkOrderContext()
        self._completed: List[WorkOrder] = []
        self._stats = {"parsed": 0, "orders": 0, "enhanced": 0, "distilled_tokens": 0,
                       "completed": 0, "spilled": 0, "summaries": 0}

    # --- Parsing ----------------------------------------------------------

    def parse(self, response_text: str, source: str = "response") -> List[WorkOrder]:
        """Parse ONLY external-tool workload from a response.

        Scans for tool-action signals; each match becomes one work
        order carrying the surrounding sentence as payload context.
        Conversational text is ignored — it never becomes an order.
        """
        self._stats["parsed"] += 1
        orders: List[WorkOrder] = []
        sentences = [s.strip() for s in response_text.replace("\n", ". ").split(".") if s.strip()]

        for sentence in sentences:
            low = sentence.lower()
            for signal, connector in EXTERNAL_SIGNALS.items():
                if signal in low:
                    orders.append(WorkOrder(
                        order_id=str(uuid.uuid4())[:10],
                        connector=connector,
                        action=signal,
                        payload={"source": source, "context": sentence[:200]},
                    ))
                    break  # one order per sentence

        self._stats["orders"] += len(orders)
        return orders

    # --- MAG enhancement ---------------------------------------------------

    def enhance(self, order: WorkOrder) -> WorkOrder:
        """Enrich an order with MAG episodic context.

        Pulls related past episodes so the order executes with the
        full weight of prior work — the 'extra possible work' the MAG
        can offer: retries that succeeded, related artifacts, similar
        past orders.
        """
        if self._mag is None:
            return order
        try:
            episodes = self._mag.recall_by_tag(order.connector)
            related = self._mag.recall_by_tag(order.action)
            order.mag_context = [
                e.get("content", "")[:120]
                for e in (episodes + related)[:4]
                if e.get("content")
            ]
            if order.mag_context:
                self._stats["enhanced"] += 1
        except Exception:
            pass
        return order

    # --- Distillation -------------------------------------------------------

    def distill(self, response_text: str, token_count: int) -> WorkOrderContext:
        """Full cycle for one response: parse → enhance → load context.

        Peak efficacy at max token: the larger the response, the more
        external workload it tends to carry; token_count is recorded
        so distillation quality tracks response size.
        """
        self.context.cycle += 1
        self.context.distilled_from_tokens += token_count
        self._stats["distilled_tokens"] += token_count

        for order in self.parse(response_text):
            self.enhance(order)
            spilled = self.context.add(order)
            if spilled is not None:
                self._stats["spilled"] += 1
                if self._backlog is not None:
                    self._backlog.defer(spilled)

            if self._mag is not None:
                try:
                    self._mag.record(
                        order.order_id,
                        f"Work order queued: {order.connector} {order.action} — {order.payload.get('context', '')[:80]}",
                        tags=[order.connector, order.action, "workorder"],
                    )
                except Exception:
                    pass

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="contexts.workorder.distilled",
                payload={
                    "cycle": self.context.cycle,
                    "orders": len(self.context.slots),
                    "tokens": token_count,
                },
                correlation_id=f"workorder_{self.context.cycle}",
            ))
        return self.context

    # --- Execution tracking (between responses) ------------------------------

    def mark(self, order_id: str, status: str, result: Any = None) -> Optional[WorkOrder]:
        """Update an order's execution state between responses."""
        for order in self.context.slots:
            if order.order_id == order_id:
                order.status = status
                order.result = result
                if status == "done":
                    self._completed.append(order)
                    self._stats["completed"] += 1
                return order
        return None

    def interjected_summary(self) -> Optional[str]:
        """Positive-framed progress summary for mid-conversation injection.

        Named 'interjected' because it appears between user-facing
        responses — the surprise payload that sparks the back-and-forth.
        """
        done = len(self._completed)
        active = len(self.context.active())
        if done == 0 and active == 0:
            return None
        self._stats["summaries"] += 1
        parts = []
        if done:
            recent = ", ".join(o.action for o in self._completed[-3:])
            parts.append(f"{done} piece(s) of work landed ({recent})")
        if active:
            parts.append(f"{active} more in flight")
        return "Quick update while we work: " + "; ".join(parts) + "."

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "context": self.context.summary()}
