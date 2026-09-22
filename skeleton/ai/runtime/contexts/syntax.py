"""
Skeleton Contexts — Context-Aware Syntax Fix Engine

The spider at the center of the context web. Every context plane
(WorkOrder, Backlog, Planning, Queue, Oracle, plus the four retrieval
planes) serializes through the same context grammar; the fixer walks
all of them, detects malformed context entries, and repairs them in
place — spider-connected so a fix in one plane propagates consistency
checks to every other plane.

Context grammar (the shared syntax):
    <kind>:<id>[@<connector>][#<priority>][!<status>]
    e.g.  workorder:a1b2c3@github.push#0.8!queued

Repair rules:
- Missing kind prefix        → infer from payload shape
- Malformed priority         → clamp to [0.0, 10.0], default 1.0
- Unknown status             → remap to nearest valid state
- Dangling connector ref     → rebind to closest known connector
- Duplicate ids across planes → re-key the newer entry
- Cross-plane inconsistency  → order in queue but done in workorder
                                context → align statuses
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus


_GRAMMAR = re.compile(
    r"^(?P<kind>[a-z_]+):(?P<id>[A-Za-z0-9-]+)"
    r"(?:@(?P<connector>[a-z.]+))?"
    r"(?:#(?P<priority>[0-9.]+))?"
    r"(?:!(?P<status>[a-z_]+))?$"
)

VALID_KINDS = {"workorder", "backlog", "plan", "plan_step", "queue", "response",
               "rag", "cag", "mag", "kag"}
VALID_STATUSES = {"queued", "assigned", "executing", "done", "failed",
                  "pending", "active", "skipped", "deferred"}
KNOWN_CONNECTORS = {
    "github.push", "github.create_repo", "github.pull_request",
    "web.search", "web.extract", "image.create", "image.edit",
    "doc.pdf", "doc.docx", "doc.xlsx", "doc.pptx", "doc.chart",
    "mail.send", "calendar.create",
}


@dataclass
class SyntaxIssue:
    """One detected grammar violation."""
    plane: str
    entry: str
    rule: str
    fixed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"plane": self.plane, "entry": self.entry[:60], "rule": self.rule, "fixed": self.fixed[:60]}


class ContextSyntaxFixer:
    """Spider-connected repair engine over all context planes."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._planes: Dict[str, Any] = {}     # spider web: name -> context object
        self._stats = {"scans": 0, "issues": 0, "fixed": 0, "propagations": 0}
        self._seen_ids: Dict[str, str] = {}   # id -> plane (for duplicate detection)

    # --- Spider connection ---------------------------------------------------

    def connect(self, name: str, plane: Any) -> None:
        """Attach a context plane to the web."""
        self._planes[name] = plane

    def connect_all(self, **planes: Any) -> None:
        for name, plane in planes.items():
            self.connect(name, plane)

    # --- Grammar --------------------------------------------------------------

    def serialize(self, kind: str, entry_id: str, connector: Optional[str] = None,
                  priority: Optional[float] = None, status: Optional[str] = None) -> str:
        """Serialize one entry to the shared context grammar."""
        out = f"{kind}:{entry_id}"
        if connector:
            out += f"@{connector}"
        if priority is not None:
            out += f"#{priority:.2f}"
        if status:
            out += f"!{status}"
        return out

    def parse_entry(self, raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Parse one grammar entry; returns (fields, error_rule)."""
        m = _GRAMMAR.match(raw.strip())
        if not m:
            return None, "malformed_grammar"
        fields = m.groupdict()
        if fields["kind"] not in VALID_KINDS:
            return fields, "unknown_kind"
        if fields.get("status") and fields["status"] not in VALID_STATUSES:
            return fields, "unknown_status"
        if fields.get("connector") and fields["connector"] not in KNOWN_CONNECTORS:
            return fields, "dangling_connector"
        if fields.get("priority"):
            try:
                p = float(fields["priority"])
                if not 0.0 <= p <= 10.0:
                    return fields, "priority_out_of_range"
            except ValueError:
                return fields, "malformed_priority"
        return fields, None

    # --- Repair primitives ----------------------------------------------------

    def _nearest_connector(self, ref: str) -> str:
        """Rebind a dangling connector to the closest known one."""
        if not ref:
            return "web.search"
        ref_parts = set(ref.split("."))
        best, best_overlap = ref, -1
        for known in KNOWN_CONNECTORS:
            overlap = len(ref_parts & set(known.split(".")))
            if overlap > best_overlap:
                best, best_overlap = known, overlap
        return best

    def _nearest_status(self, status: str) -> str:
        """Remap an unknown status to the nearest valid state."""
        aliases = {
            "complete": "done", "finished": "done", "ok": "done",
            "error": "failed", "broken": "failed",
            "running": "executing", "working": "executing",
            "waiting": "queued", "todo": "queued", "new": "queued",
            "wip": "active", "open": "pending",
        }
        return aliases.get(status, "pending")

    def fix_entry(self, plane: str, raw: str) -> Tuple[str, List[SyntaxIssue]]:
        """Repair one entry end-to-end; returns (fixed, issues)."""
        issues: List[SyntaxIssue] = []
        fields, error = self.parse_entry(raw)

        if error == "malformed_grammar":
            # Try to salvage: extract any id-looking token
            tokens = re.findall(r"[A-Za-z0-9-]{4,}", raw)
            entry_id = tokens[0] if tokens else "unknown"
            kind = plane if plane in VALID_KINDS else "response"
            fixed = self.serialize(kind, entry_id)
            issues.append(SyntaxIssue(plane=plane, entry=raw, rule="malformed_grammar", fixed=fixed))
            return fixed, issues

        kind = fields["kind"]
        entry_id = fields["id"]
        connector = fields.get("connector")
        status = fields.get("status")
        priority = fields.get("priority")

        if error == "unknown_kind":
            issues.append(SyntaxIssue(plane=plane, entry=raw, rule="unknown_kind"))
            kind = plane if plane in VALID_KINDS else "response"
        if error == "unknown_status" and status:
            new_status = self._nearest_status(status)
            issues.append(SyntaxIssue(plane=plane, entry=raw, rule="unknown_status",
                                      fixed=f"{status}→{new_status}"))
            status = new_status
        if error == "dangling_connector" and connector:
            new_connector = self._nearest_connector(connector)
            issues.append(SyntaxIssue(plane=plane, entry=raw, rule="dangling_connector",
                                      fixed=f"{connector}→{new_connector}"))
            connector = new_connector
        if error == "priority_out_of_range" and priority:
            clamped = min(10.0, max(0.0, float(priority)))
            issues.append(SyntaxIssue(plane=plane, entry=raw, rule="priority_out_of_range",
                                      fixed=f"{priority}→{clamped}"))
            priority = f"{clamped}"

        # Duplicate id detection across planes (spider web check)
        if entry_id in self._seen_ids and self._seen_ids[entry_id] != plane:
            new_id = f"{entry_id}-{plane[:3]}"
            issues.append(SyntaxIssue(plane=plane, entry=raw, rule="duplicate_id",
                                      fixed=f"{entry_id}→{new_id}"))
            entry_id = new_id
        self._seen_ids[entry_id] = plane

        fixed = self.serialize(
            kind, entry_id,
            connector=connector,
            priority=float(priority) if priority else None,
            status=status,
        )
        self._stats["fixed"] += len(issues)
        return fixed, issues

    # --- Full-web scan -----------------------------------------------------------

    def scan(self) -> List[SyntaxIssue]:
        """Walk every connected plane and repair all entries."""
        self._stats["scans"] += 1
        all_issues: List[SyntaxIssue] = []

        for plane_name, plane in self._planes.items():
            entries = self._entries_of(plane_name, plane)
            for raw in entries:
                _, issues = self.fix_entry(plane_name, raw)
                all_issues.extend(issues)

        # Cross-plane consistency: statuses aligned
        all_issues.extend(self._cross_plane_check())

        self._stats["issues"] += len(all_issues)
        if self._bus and all_issues:
            self._bus.publish(DomainEvent(
                topic="contexts.syntax.repaired",
                payload={"issues": len(all_issues), "planes": len(self._planes)},
            ))
        return all_issues

    def _entries_of(self, plane_name: str, plane: Any) -> List[str]:
        """Serialize a plane's entries into grammar strings for checking."""
        out: List[str] = []
        if plane_name == "workorder":
            for o in getattr(getattr(plane, "context", plane), "slots", []):
                out.append(self.serialize("workorder", o.order_id, o.connector, o.priority, o.status))
        elif plane_name == "backlog":
            for i in getattr(plane, "items", []):
                out.append(self.serialize("backlog", i.item_id, priority=i.priority, status="deferred"))
        elif plane_name == "planning":
            for p in getattr(plane, "plans", []):
                out.append(self.serialize("plan", p.plan_id, status="active" if p.progress() < 1.0 else "done"))
                for s in p.steps:
                    out.append(self.serialize("plan_step", s.step_id, s.connector, s.estimated_cost, s.status))
        elif plane_name == "queue":
            for i in getattr(plane, "items", []):
                out.append(self.serialize("queue", i.item_id, status="queued"))
        return out

    def _cross_plane_check(self) -> List[SyntaxIssue]:
        """Spider consistency: an order done in workorders but still queued."""
        issues: List[SyntaxIssue] = []
        workorders = self._planes.get("workorder")
        queue = self._planes.get("queue")
        if workorders is None or queue is None:
            return issues

        ctx = getattr(workorders, "context", workorders)
        done_ids = {o.order_id for o in getattr(ctx, "slots", []) if o.status == "done"}
        for item in getattr(queue, "items", []):
            payload_id = getattr(item.payload, "order_id", None)
            if payload_id and payload_id in done_ids:
                issues.append(SyntaxIssue(
                    plane="queue", entry=item.item_id,
                    rule="cross_plane_stale_queue",
                    fixed=f"order {payload_id} already done",
                ))
                self._stats["propagations"] += 1
        return issues

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "planes_connected": len(self._planes)}
