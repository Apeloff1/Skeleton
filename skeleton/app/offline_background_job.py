"""Bounded local reference job.

The planner is deterministic. It may read the local library and, only when
the run is opened with writes allowed, propose one approved write. The
canonical background agent enforces the step budget and refuses nested
fan-out before any tool runs. This is not a model planner and it does not
grant writes by itself.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.app.offline_reference_read import (
    TOOL_ID as READ_TOOL,
    LocalReferenceRead,
    ReferenceReadDenied,
)
from skeleton.app.offline_reference_write import (
    TOOL_ID as WRITE_TOOL,
    LocalReferenceWrite,
    _body,
    _title,
)
from skeleton.intelligence.background_agent import AgentStep, BackgroundAgent


SCHEMA = "skeleton.app.local_reference_job.v1"
MAX_STEPS = 2
MAX_CHILDREN = 0


class LocalJobRejected(ValueError):
    """The local job request is outside its bound."""


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise LocalJobRejected("request id must be a canonical UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise LocalJobRejected("request id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise LocalJobRejected("request id must be a canonical UUID")
    return value


class LocalReferenceJob:
    """One read, and at most one approved write, inside the agent budget."""

    def __init__(self, library: OfflineKnowledgeLibrary) -> None:
        if not isinstance(library, OfflineKnowledgeLibrary):
            raise TypeError("library must be an OfflineKnowledgeLibrary")
        self.library = library
        self.reads = LocalReferenceRead(library)
        self.writes = LocalReferenceWrite(library)

    def run(
        self,
        goal: object,
        request_id: object,
        *,
        granted: object,
        allow_writes: object,
        title: object = None,
        text: object = None,
        approval_ref: object = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if type(allow_writes) is not bool:
            raise LocalJobRejected("allow_writes must be a boolean")
        if type(granted) is not bool:
            raise LocalJobRejected("granted must be a boolean")
        if granted is not True:
            raise ReferenceReadDenied("reference reads require an explicit operator grant")
        if not isinstance(goal, str) or not goal.strip():
            raise LocalJobRejected("goal must contain text")
        identity = _uuid(request_id)
        write_requested = title is not None or text is not None or approval_ref is not None
        if write_requested and not allow_writes:
            return self._stopped(
                "blocked",
                "writes are not allowed for this job",
                allow_writes=False,
            )
        normalized_title = None
        normalized_text = None
        if allow_writes:
            if title is None or text is None:
                raise LocalJobRejected("an approved write requires title and text")
            normalized_title = _title(title)
            normalized_text = _body(text)
        parent = UUID(identity)
        read_id = str(uuid5(parent, "read"))
        write_id = str(uuid5(parent, "write"))
        outcomes: dict[str, dict[str, Any] | None] = {"read": None, "write": None}

        def planner(current: str, calls: tuple[str, ...]) -> AgentStep | None:
            if len(calls) >= MAX_STEPS:
                return None
            if not calls:
                return AgentStep(READ_TOOL, {"query": current, "request_id": read_id})
            if allow_writes and calls == (READ_TOOL,):
                return AgentStep(WRITE_TOOL, {
                    "title": normalized_title,
                    "text": normalized_text,
                    "request_id": write_id,
                })
            return None

        def executor(step: AgentStep) -> str:
            if step.tool == READ_TOOL:
                result = self.reads.read(
                    step.arguments["query"], step.arguments["request_id"],
                    granted=True, now=now,
                )
                outcomes["read"] = result
                if result["status"] != "succeeded":
                    return "denied:" + str(result["error_code"] or result["status"])
                return "receipt:" + result["receipt_id"]
            result = self.writes.write(
                step.arguments["title"], step.arguments["text"], step.arguments["request_id"],
                approved=True, approval_ref=approval_ref, now=now,
            )
            outcomes["write"] = result
            if result["status"] != "succeeded":
                return "denied:" + str(result["error_code"] or result["status"])
            return "receipt:" + result["receipt_id"]

        # One extra step lets the planner return None after the last tool call.
        # The planner itself never emits more than MAX_STEPS calls.
        agent = BackgroundAgent(
            max_steps=(MAX_STEPS if allow_writes else 1) + 1,
            max_children=MAX_CHILDREN,
            allow_writes=allow_writes,
        )
        result = agent.run(goal, planner, executor)
        status = result.status
        write = outcomes["write"]
        if write is not None and write.get("error_code") == "approval_required":
            status = "waiting_for_approval"
        elif write is not None and write.get("status") != "succeeded":
            status = "denied"
        return {
            "schema": SCHEMA,
            "status": status,
            "steps": result.steps,
            "calls": list(result.calls),
            "reason": result.reason,
            "allow_writes": allow_writes,
            "max_steps": MAX_STEPS,
            "max_children": MAX_CHILDREN,
            "read": outcomes["read"],
            "write": write,
        }

    def _stopped(self, status: str, reason: str, *, allow_writes: bool) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": status,
            "steps": 0,
            "calls": [],
            "reason": reason,
            "allow_writes": allow_writes,
            "max_steps": MAX_STEPS,
            "max_children": MAX_CHILDREN,
            "read": None,
            "write": None,
        }
