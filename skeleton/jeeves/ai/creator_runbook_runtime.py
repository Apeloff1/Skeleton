"""Executable Jeeves creator runbooks through the EXISTING host ToolExecutor.

No new tool authority is invented. Every step must receive a fresh, expiring,
exact-argument HIGH_IMPACT ToolGrant and the registered creator handler must
also pass the host's exact CreatorCommand authorization callback.

Persistence is mandatory before invoking a non-idempotent effect. An in-flight
step recovered from a crash requires explicit IN_DOUBT reconciliation and is never automatically retried.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from skeleton.forge.creator.command_surface import (
    CreatorCommand, CreatorCommandReceipt, build_creator_command,
    validate_creator_receipt,
)
from skeleton.jeeves.agent.tools import ToolExecutionContext, ToolExecutor, ToolGrant
from skeleton.jeeves.agent.types import RiskTier, ToolCall, stable_fingerprint


class CreatorRunbookError(ValueError):
    """Invalid plan, authorization, state transition or uncertain effect."""


class RunbookState(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    IN_DOUBT = "in_doubt"
    ABORTED = "aborted"


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(raw) > 256 * 1024:
        raise CreatorRunbookError("runbook payload exceeds byte budget")
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class CreatorRunbookStep:
    step_id: str
    command: CreatorCommand
    after: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest({
            "step_id": self.step_id, "command": self.command.to_dict(),
            "after": list(self.after),
        })


@dataclass(frozen=True, slots=True)
class RunbookStepStatus:
    step_id: str
    status: RunbookState
    attempts: int = 0
    receipt_digest: str | None = None
    observation_digest: str | None = None
    outcome_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id, "status": self.status.value,
            "attempts": self.attempts, "receipt_digest": self.receipt_digest,
            "observation_digest": self.observation_digest,
            "outcome_reason": self.outcome_reason,
        }


class CreatorRunbook:
    """Verified typed representation of a Jeeves creator.plan output."""

    def __init__(self, plan: Mapping[str, Any]) -> None:
        if not isinstance(plan, Mapping) or plan.get("kind") != "creator-plan":
            raise CreatorRunbookError("runbook requires a creator-plan proposal")
        if plan.get("execution_authority") != "none" or plan.get("dispatch_performed") is not False:
            raise CreatorRunbookError("creator plan was not a non-executing proposal")
        steps = plan.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
            raise CreatorRunbookError("creator plan must contain 1..32 steps")
        if _digest(steps) != plan.get("plan_sha256"):
            raise CreatorRunbookError("creator plan digest mismatch")
        seen: set[str] = set()
        result: list[CreatorRunbookStep] = []
        project_id = plan.get("project_id")
        for index, entry in enumerate(steps):
            if not isinstance(entry, dict) or set(entry) != {
                "index", "step_id", "after", "command", "dispatch_performed",
            }:
                raise CreatorRunbookError("creator plan step schema mismatch")
            step_id, after, command_data = (
                entry["step_id"], entry["after"], entry["command"],
            )
            if (entry["index"] != index or type(entry["index"]) is not int
                    or not isinstance(step_id, str) or not step_id
                    or len(step_id) > 128 or step_id in seen
                    or not isinstance(after, list) or len(after) > 32
                    or any(not isinstance(dep, str) or dep not in seen for dep in after)
                    or len(after) != len(set(after))
                    or entry["dispatch_performed"] is not False):
                raise CreatorRunbookError("creator plan is not ordered, unique or bounded")
            if not isinstance(command_data, dict) or set(command_data) != {
                "schema", "schema_version", "operation", "project_id",
                "payload", "digest",
            }:
                raise CreatorRunbookError("creator command contract mismatch")
            command = build_creator_command(
                command_data["operation"], project_id=command_data["project_id"],
                payload=command_data["payload"],
            )
            if (command.to_dict() != command_data
                    or command.project_id != project_id):
                raise CreatorRunbookError("creator plan includes unbound or altered command")
            result.append(CreatorRunbookStep(step_id, command, tuple(after)))
            seen.add(step_id)
        self.project_id = project_id
        self.plan_sha256 = plan["plan_sha256"]
        self.steps = tuple(result)
        self._by_id = {step.step_id: step for step in self.steps}

    def get(self, step_id: str) -> CreatorRunbookStep:
        try:
            return self._by_id[step_id]
        except KeyError as exc:
            raise CreatorRunbookError("unknown runbook step") from exc


# The persistence callback must compare-and-swap old/new heads atomically in a
# host-owned durable store; it returns exactly True only after the new state is
# durably committed. A model must not supply or impersonate this callback.
RunbookPersist = Callable[[dict[str, Any], str | None], bool]


class CreatorRunbookRunner:
    """One bounded step at a time; no implicit retries or self-authority."""

    def __init__(
        self,
        plan: CreatorRunbook,
        *,
        executor: ToolExecutor,
        persist: RunbookPersist,
        restored: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(plan, CreatorRunbook):
            raise CreatorRunbookError("plan must be CreatorRunbook")
        if not isinstance(executor, ToolExecutor):
            raise CreatorRunbookError("runbook requires the host's ToolExecutor")
        if not callable(persist):
            raise CreatorRunbookError("durable compare-and-swap persistence is required")
        self.plan = plan
        self.executor = executor
        self.persist = persist
        self._lock = RLock()
        self._statuses = {
            step.step_id: RunbookStepStatus(step.step_id, RunbookState.PENDING)
            for step in plan.steps
        }
        self._head: str | None = None
        if restored is not None:
            self._restore(restored)

    def _snapshot(self, statuses: Mapping[str, RunbookStepStatus]) -> dict[str, Any]:
        rows = [statuses[step.step_id].as_dict() for step in self.plan.steps]
        payload = {
            "schema": "jeeves.creator_runbook_execution.v1",
            "plan_sha256": self.plan.plan_sha256,
            "project_id": self.plan.project_id,
            "steps": rows,
            "execution_authority": "host-tool-executor-only",
        }
        payload["head_digest"] = _digest(payload)
        return payload

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot(self._statuses)

    def _restore(self, state: Mapping[str, Any]) -> None:
        if not isinstance(state, Mapping) or set(state) != {
            "schema", "plan_sha256", "project_id", "steps",
            "execution_authority", "head_digest",
        }:
            raise CreatorRunbookError("persisted runbook schema mismatch")
        if (state["schema"] != "jeeves.creator_runbook_execution.v1"
                or state["plan_sha256"] != self.plan.plan_sha256
                or state["project_id"] != self.plan.project_id
                or state["execution_authority"] != "host-tool-executor-only"):
            raise CreatorRunbookError("runbook state belongs to another plan")
        payload = dict(state)
        head = payload.pop("head_digest")
        if _digest(payload) != head:
            raise CreatorRunbookError("runbook state digest mismatch")
        rows = state["steps"]
        if not isinstance(rows, list) or len(rows) != len(self.plan.steps):
            raise CreatorRunbookError("runbook state lost a step")
        loaded: dict[str, RunbookStepStatus] = {}
        for step, item in zip(self.plan.steps, rows):
            if not isinstance(item, dict) or set(item) != {
                "step_id", "status", "attempts", "receipt_digest",
                "observation_digest", "outcome_reason",
            } or item["step_id"] != step.step_id:
                raise CreatorRunbookError("runbook step state identity changed")
            try:
                status = RunbookState(item["status"])
            except (TypeError, ValueError) as exc:
                raise CreatorRunbookError("invalid persisted runbook state") from exc
            attempts = item["attempts"]
            if type(attempts) is not int or not 0 <= attempts <= 1:
                raise CreatorRunbookError("invalid runbook attempt count")
            for key in ("receipt_digest", "observation_digest"):
                val = item[key]
                if val is not None and (not isinstance(val, str) or len(val) != 64
                                        or any(c not in "0123456789abcdef" for c in val)):
                    raise CreatorRunbookError("invalid runbook evidence digest")
            if status is RunbookState.SUCCEEDED and not item["receipt_digest"]:
                raise CreatorRunbookError("successful runbook step lacks receipt")
            if status is RunbookState.PENDING and attempts != 0:
                raise CreatorRunbookError("pending step has already been dispatched")
            loaded[step.step_id] = RunbookStepStatus(
                step.step_id, status, attempts, item["receipt_digest"],
                item["observation_digest"], item["outcome_reason"],
            )
        for step in self.plan.steps:
            if loaded[step.step_id].status is RunbookState.SUCCEEDED:
                if any(loaded[dep].status is not RunbookState.SUCCEEDED for dep in step.after):
                    raise CreatorRunbookError("persisted runbook has unsatisfied dependencies")
        self._statuses = loaded
        self._head = head

    def ready(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(step.step_id for step in self.plan.steps
                         if self._statuses[step.step_id].status is RunbookState.PENDING
                         and all(self._statuses[dep].status is RunbookState.SUCCEEDED
                                 for dep in step.after))

    def _persist(self, statuses: Mapping[str, RunbookStepStatus]) -> None:
        snapshot = self._snapshot(statuses)
        if self.persist(snapshot, self._head) is not True:
            raise CreatorRunbookError("durable workflow state commit denied")
        self._statuses = dict(statuses)
        self._head = snapshot["head_digest"]

    def reconcile_in_flight(self, step_id: str, *, evidence_digest: str,
                            reason: str = "uncertain_effect") -> RunbookStepStatus:
        """Quarantine in-flight work. A new run may not replay the old effect."""
        with self._lock:
            current = self._statuses[self.plan.get(step_id).step_id]
            if current.status is not RunbookState.IN_FLIGHT:
                raise CreatorRunbookError("only in-flight work can be quarantined")
            if (not isinstance(evidence_digest, str) or len(evidence_digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in evidence_digest)):
                raise CreatorRunbookError("quarantine requires SHA-256 evidence digest")
            item = RunbookStepStatus(
                step_id, RunbookState.IN_DOUBT, current.attempts,
                observation_digest=evidence_digest, outcome_reason=reason[:128],
            )
            updated = dict(self._statuses)
            updated[step_id] = item
            self._persist(updated)
            return item

    def reconcile_effect(
        self, step_id: str, *,
        verifier_id: str,
        proof_digest: str,
        verify_external: Callable[
            [CreatorRunbookStep, CreatorCommandReceipt | None, str, str], bool
        ],
        receipt: CreatorCommandReceipt | None = None,
    ) -> RunbookStepStatus:
        """Independently settle an uncertain effect without invoking it again.

        A verified command receipt resolves the step as succeeded. An absence
        receipt verified by the external owner can close it as ABORTED; neither
        outcome authorizes a new attempt of that non-idempotent command.
        """
        if (not isinstance(verifier_id, str) or not verifier_id.strip()
                or len(verifier_id) > 192):
            raise CreatorRunbookError("independent verifier identity required")
        if (not isinstance(proof_digest, str) or len(proof_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in proof_digest)):
            raise CreatorRunbookError("external effect proof must be SHA-256")
        if not callable(verify_external):
            raise CreatorRunbookError("host external-effect verifier required")
        with self._lock:
            step = self.plan.get(step_id)
            prior = self._statuses[step_id]
            if prior.status not in (RunbookState.IN_DOUBT, RunbookState.IN_FLIGHT):
                raise CreatorRunbookError("only uncertain or in-flight effects can be settled")
            if receipt is not None:
                if not isinstance(receipt, CreatorCommandReceipt):
                    raise CreatorRunbookError("typed external creator receipt required")
                validate_creator_receipt(receipt, step.command)
            outcome = "completed" if receipt is not None else "confirmed_no_effect"
            if verify_external(step, receipt, proof_digest, verifier_id) is not True:
                raise CreatorRunbookError("independent host could not settle external effect")
            evidence = _digest({
                "step_id": step_id, "command_digest": step.command.digest,
                "previous_status": prior.status.value,
                "prior_observation": prior.observation_digest,
                "verifier_id": verifier_id, "proof_digest": proof_digest,
                "receipt_digest": receipt.digest if receipt is not None else None,
                "outcome": outcome,
            })
            settled = RunbookStepStatus(
                step_id=step_id,
                status=RunbookState.SUCCEEDED if receipt else RunbookState.ABORTED,
                attempts=prior.attempts,
                receipt_digest=receipt.digest if receipt is not None else None,
                observation_digest=evidence, outcome_reason=outcome,
            )
            revised = dict(self._statuses)
            revised[step_id] = settled
            self._persist(revised)
            return settled

    def execute_step(self, step_id: str, *, context: ToolExecutionContext,
                     grant: ToolGrant) -> RunbookStepStatus:
        """Execute one explicitly granted exact command through the host gate."""
        with self._lock:
            step = self.plan.get(step_id)
            if step_id not in self.ready():
                raise CreatorRunbookError("runbook step is not ready")
            if not isinstance(context, ToolExecutionContext) or not isinstance(grant, ToolGrant):
                raise CreatorRunbookError("host execution context and grant required")
            arguments = {
                "operation": step.command.operation,
                "project_id": step.command.project_id,
                "payload": dict(step.command.payload),
            }
            if (grant.tool_name != "creator_execute_authorized"
                    or RiskTier.HIGH_IMPACT not in grant.allowed_risks
                    or grant.argument_fingerprint != stable_fingerprint(arguments)
                    or grant.expires_at is None or grant.max_calls != 1):
                raise CreatorRunbookError("exact one-shot creator permission is required")
            updated = dict(self._statuses)
            updated[step_id] = RunbookStepStatus(
                step_id, RunbookState.IN_FLIGHT, attempts=1,
            )
            # Commit intent before any call that may mutate the application.
            self._persist(updated)
            call = ToolCall(
                call_id="creator-" + _digest([
                    self.plan.plan_sha256, step_id, context.run_id,
                ])[:32],
                name="creator_execute_authorized",
                arguments=arguments,
                reason="host-authorized creator runbook step",
            )
            try:
                result = self.executor.execute(call, context, grants=(grant,))
            except BaseException:
                # The action may have been observed by an external handler.
                # Never auto retry this non-idempotent step.
                raise
            receipt_digest = None
            if result.ok and isinstance(result.payload, Mapping):
                try:
                    payload = result.payload
                    receipt = CreatorCommandReceipt(
                        command_digest=payload["command_digest"],
                        operation=payload["operation"],
                        status=payload["status"],
                        output=payload["output"],
                        digest=payload["digest"],
                    )
                    validate_creator_receipt(receipt, step.command)
                    receipt_digest = receipt.digest
                except (KeyError, TypeError, ValueError):
                    receipt_digest = None
            observation_digest = _digest({
                "call_id": result.call_id, "tool_name": result.tool_name,
                "ok": result.ok, "cached": result.cached,
                "receipt_digest": receipt_digest,
                "error_type_digest": _digest(result.error or ""),
            })
            next_state = (
                RunbookState.SUCCEEDED if receipt_digest is not None
                else RunbookState.IN_DOUBT
            )
            updated[step_id] = RunbookStepStatus(
                step_id, next_state, attempts=1,
                receipt_digest=receipt_digest, observation_digest=observation_digest,
                outcome_reason="completed" if receipt_digest else "external_effect_uncertain",
            )
            self._persist(updated)
            return updated[step_id]


__all__ = [
    "CreatorRunbookError", "RunbookState", "CreatorRunbookStep",
    "RunbookStepStatus", "CreatorRunbook", "CreatorRunbookRunner",
]
