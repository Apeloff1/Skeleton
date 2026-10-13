"""One-step Jeeves plan execution under durable authority and live app grants.

Bridges the existing non-executing orchestration contract to the existing
owner-bound tool runtime. A plan task must include the exact capability intent
digest in its immutable payload; readiness and host authorization are separately
checked at dispatch time.

Effects cannot be retried automatically after a failed/unknown ToolObservation,
a process crash, or failure to durably acknowledge the outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Callable

from skeleton.jeeves.ai.contracts import Authority
from skeleton.jeeves.ai.orchestration import OrchestrState
from skeleton.jeeves.ai.orchestration_store import DurableOrchestrLedger
from skeleton.jeeves.agent.capability_dispatch import (
    AppDispatchError, CapabilityIntent, JeevesCapabilityDispatcher,
)
from skeleton.jeeves.agent.tools import ToolExecutionContext, ToolGrant, ToolObservation


class OrchestratedDispatchError(ValueError):
    """Plan state, exact intent, evidence or host authority mismatch."""


def _digest(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(encoded) > 1024 * 1024:
        raise OrchestratedDispatchError("orchestrated evidence exceeds byte budget")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class OrchestratedDispatchReceipt:
    task_name: str
    request_digest: str
    observation_digest: str
    plan_event_digest: str
    outcome: str
    tool_ok: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "jeeves.orchestrated_capability_receipt.v1",
            "task_name": self.task_name, "request_digest": self.request_digest,
            "observation_digest": self.observation_digest,
            "plan_event_digest": self.plan_event_digest,
            "outcome": self.outcome, "tool_ok": self.tool_ok,
        }


class JeevesOrchestratedCapabilityRuntime:
    """Execute exactly one prepared task. Never invent delegated grants."""

    def __init__(
        self, *,
        ledger: DurableOrchestrLedger,
        dispatcher: JeevesCapabilityDispatcher,
        verify_result: Callable[[CapabilityIntent, ToolObservation, ToolExecutionContext], str | None],
    ) -> None:
        if not isinstance(ledger, DurableOrchestrLedger):
            raise OrchestratedDispatchError("durable host-owned orchestration ledger required")
        if not isinstance(dispatcher, JeevesCapabilityDispatcher):
            raise OrchestratedDispatchError("owner-bound host dispatcher required")
        if not callable(verify_result):
            raise OrchestratedDispatchError("independent host outcome verifier required")
        self.ledger = ledger
        self.dispatcher = dispatcher
        self.verify_result = verify_result

    def ready(self) -> tuple[str, ...]:
        """List the exact durable plan tasks eligible to begin."""
        ledger, _head, _count = self.ledger.load()
        return ledger.ready_names()

    def dispatch_one(
        self, task_name: str,
        intent: CapabilityIntent, *,
        context: ToolExecutionContext,
        grant: ToolGrant,
        actor: str,
        authority: Authority,
        expected_plan_head: str,
        at_ns: int,
    ) -> OrchestratedDispatchReceipt:
        """Run one READY task and durably classify the external tool outcome."""
        if not isinstance(intent, CapabilityIntent):
            raise OrchestratedDispatchError("typed capability intent required")
        if not isinstance(context, ToolExecutionContext):
            raise OrchestratedDispatchError("host execution context required")
        if type(at_ns) is not int or at_ns < 0:
            raise OrchestratedDispatchError("dispatch time must be host-observed nanoseconds")
        ledger, actual_head, _revision = self.ledger.load()
        if expected_plan_head != actual_head:
            raise OrchestratedDispatchError("plan head changed since admission")
        task = next((row for row in ledger.records if row.name == task_name), None)
        if task is None or task.state is not OrchestrState.READY:
            raise OrchestratedDispatchError("task must be explicitly READY")
        if task_name not in ledger.ready_names():
            raise OrchestratedDispatchError("task dependencies or delegation prevent dispatch")
        if task.authority is not authority and authority is Authority.WORKER:
            raise OrchestratedDispatchError("worker cannot execute a higher-authority task")
        if authority is Authority.SECRETARY and task.authority is Authority.SUPERVISOR:
            raise OrchestratedDispatchError("secretary cannot execute supervisor tasks")
        if task.payload.get("capability_intent_digest") != intent.digest:
            raise OrchestratedDispatchError("plan does not bind the exact capability intent")
        if task.payload.get("run_id") != context.run_id:
            raise OrchestratedDispatchError("task binds another execution run")
        if task.payload.get("project_id") != intent.project_id:
            raise OrchestratedDispatchError("task binds another application project")
        # Changing the task to RUNNING is durably committed *before* the
        # ToolExecutor may invoke a non-idempotent host handler.
        ledger, running_head = self.ledger.transition(
            task_name, OrchestrState.RUNNING, evidence=(intent.digest,),
            actor=actor, authority=authority, proof_digest=intent.digest,
            at_ns=at_ns, expected_head=actual_head,
        )
        try:
            observation = self.dispatcher.execute(
                intent, context=context, grant=grant, now_ns=at_ns,
            )
        except BaseException:
            # A remote effect may have occurred before an exception arrived.
            # Retain RUNNING to block a blind retry. Host reconciliation must
            # attach an externally verified receipt before any new attempt.
            raise
        # Only an independent, host-supplied receipt verifier can complete a
        # task. Tool success alone does not prove the intended app effect.
        qualification = self.verify_result(intent, observation, context)
        if qualification is not None and (
            not isinstance(qualification, str) or len(qualification) != 64
            or any(ch not in "0123456789abcdef" for ch in qualification)
        ):
            raise OrchestratedDispatchError("invalid host completion evidence digest")
        observation_digest = _digest({
            "host_qualification_digest": qualification,
            "call_id": observation.call_id,
            "tool_name": observation.tool_name,
            "ok": observation.ok,
            "cached": observation.cached,
            "payload_digest": _digest(observation.payload),
            "error_digest": _digest(observation.error),
        })
        confirmed = observation.ok and qualification is not None
        next_state = OrchestrState.DONE if confirmed else OrchestrState.BLOCKED
        _ledger, terminal_head = self.ledger.transition(
            task_name, next_state,
            evidence=(observation_digest,),
            actor=actor, authority=authority,
            proof_digest=observation_digest, at_ns=at_ns,
            expected_head=running_head,
        )
        return OrchestratedDispatchReceipt(
            task_name=task_name, request_digest=intent.digest,
            observation_digest=observation_digest,
            plan_event_digest=terminal_head,
            outcome="completed" if confirmed else "in_doubt",
            tool_ok=observation.ok,
        )


__all__ = [
    "OrchestratedDispatchError", "OrchestratedDispatchReceipt",
    "JeevesOrchestratedCapabilityRuntime",
]
