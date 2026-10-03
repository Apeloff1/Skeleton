"""Deterministic multi-volume planning for the deferred AI execution kernel.

Plans are content-addressed DAGs.  They never imply transactional rollback:
steps run only after their dependencies succeed, execution stops on the first
failure, and the plan receipt records exactly which durable operation receipts
were completed before the stop.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .contracts import canonical_json, sha256_json
from .executor import (
    DeferredExecutionError,
    DeferredExecutor,
    ExecutionOutcome,
)

_VOLUME_RE = re.compile(r"^VOL-\d{3}$")


def _text(value: object, name: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{name} must be at most {max_length} characters")
    if any(ord(ch) < 32 for ch in normalized):
        raise ValueError(f"{name} must not contain control characters")
    return normalized


def _units(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class DeferredPlanStep:
    step_id: str
    volume_id: str
    operation_id: str
    payload_json: str
    payload_digest: str
    cost_units: int = 0
    latency_ms: int = 0
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_id",
            _text(self.step_id, "step_id", max_length=128),
        )
        volume_id = _text(self.volume_id, "volume_id", max_length=7)
        if not _VOLUME_RE.fullmatch(volume_id):
            raise ValueError("volume_id must be VOL-NNN")
        object.__setattr__(self, "volume_id", volume_id)
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id"),
        )
        if not isinstance(self.payload_json, str):
            raise TypeError("payload_json must be text")
        try:
            decoded = json.loads(self.payload_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload_json must be valid JSON") from exc
        if not isinstance(decoded, dict):
            raise ValueError("plan step payload must decode to an object")
        canonical = canonical_json(decoded)
        if canonical != self.payload_json:
            raise ValueError("payload_json must use canonical JSON encoding")
        expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if self.payload_digest != expected_digest:
            raise ValueError("payload_digest does not match payload_json")
        object.__setattr__(
            self,
            "cost_units",
            _units(self.cost_units, "cost_units"),
        )
        object.__setattr__(
            self,
            "latency_ms",
            _units(self.latency_ms, "latency_ms"),
        )
        deps = tuple(
            _text(item, "depends_on", max_length=128)
            for item in self.depends_on
        )
        if len(deps) != len(set(deps)):
            raise ValueError("depends_on values must be unique")
        if self.step_id in deps:
            raise ValueError("plan step cannot depend on itself")
        object.__setattr__(self, "depends_on", deps)

    @classmethod
    def create(
        cls,
        *,
        step_id: str,
        volume_id: str,
        operation_id: str,
        payload: Mapping[str, Any],
        cost_units: int = 0,
        latency_ms: int = 0,
        depends_on: Iterable[str] = (),
    ) -> "DeferredPlanStep":
        digest = DeferredExecutor.digest_payload(payload)
        payload_json = canonical_json(dict(payload))
        return cls(
            step_id=step_id,
            volume_id=volume_id,
            operation_id=operation_id,
            payload_json=payload_json,
            payload_digest=digest,
            cost_units=cost_units,
            latency_ms=latency_ms,
            depends_on=tuple(depends_on),
        )

    def payload(self) -> dict[str, Any]:
        value = json.loads(self.payload_json)
        if not isinstance(value, dict):
            raise RuntimeError("validated plan payload no longer decodes to object")
        return value

    def as_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "volume_id": self.volume_id,
            "operation_id": self.operation_id,
            "payload_digest": self.payload_digest,
            "cost_units": self.cost_units,
            "latency_ms": self.latency_ms,
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True, slots=True)
class DeferredPlan:
    plan_id: str
    steps: tuple[DeferredPlanStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan_id",
            _text(self.plan_id, "plan_id", max_length=256),
        )
        steps = tuple(self.steps)
        if not steps:
            raise ValueError("deferred plan must contain at least one step")
        if any(not isinstance(step, DeferredPlanStep) for step in steps):
            raise TypeError("steps must contain DeferredPlanStep values")

        step_ids = [step.step_id for step in steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("plan step ids must be unique")
        operation_ids = [step.operation_id for step in steps]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("plan operation ids must be unique")

        known = set(step_ids)
        for step in steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(
                    f"{step.step_id}: unknown dependencies "
                    + ",".join(sorted(missing))
                )

        by_id = {step.step_id: step for step in steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("deferred plan dependency cycle detected")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id].depends_on:
                walk(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in sorted(by_id):
            walk(step_id)

        object.__setattr__(self, "steps", steps)

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "plan_id": self.plan_id,
                "steps": [
                    step.as_dict()
                    for step in sorted(self.steps, key=lambda item: item.step_id)
                ],
            }
        )

    def ordered_steps(self) -> tuple[DeferredPlanStep, ...]:
        by_id = {step.step_id: step for step in self.steps}
        remaining = set(by_id)
        complete: set[str] = set()
        ordered: list[DeferredPlanStep] = []

        while remaining:
            ready = sorted(
                (
                    step_id
                    for step_id in remaining
                    if set(by_id[step_id].depends_on).issubset(complete)
                )
            )
            if not ready:
                raise RuntimeError("validated deferred plan became unschedulable")
            for step_id in ready:
                ordered.append(by_id[step_id])
                complete.add(step_id)
                remaining.remove(step_id)

        return tuple(ordered)


@dataclass(frozen=True, slots=True)
class DeferredPlanReceipt:
    plan_id: str
    plan_digest: str
    status: str
    completed: tuple[tuple[str, str], ...]
    failure_step_id: str | None = None
    failure_digest: str | None = None
    operation_failure_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan_id",
            _text(self.plan_id, "plan_id", max_length=256),
        )
        if (
            not isinstance(self.plan_digest, str)
            or len(self.plan_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.plan_digest)
        ):
            raise ValueError("plan_digest must be lowercase sha256")
        if self.status not in {"succeeded", "failed"}:
            raise ValueError("unsupported plan receipt status")

        seen: set[str] = set()
        normalized: list[tuple[str, str]] = []
        for step_id, receipt_digest in self.completed:
            step_id = _text(step_id, "completed step id", max_length=128)
            if step_id in seen:
                raise ValueError("completed step ids must be unique")
            seen.add(step_id)
            if (
                not isinstance(receipt_digest, str)
                or len(receipt_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in receipt_digest)
            ):
                raise ValueError("completed receipt digests must be sha256")
            normalized.append((step_id, receipt_digest))
        object.__setattr__(self, "completed", tuple(normalized))

        if self.status == "succeeded":
            if (
                self.failure_step_id is not None
                or self.failure_digest is not None
                or self.operation_failure_receipt_digest is not None
            ):
                raise ValueError("successful plan receipt cannot contain failure data")
        else:
            if self.failure_step_id is None or self.failure_digest is None:
                raise ValueError("failed plan receipt requires failure identity")
            object.__setattr__(
                self,
                "failure_step_id",
                _text(self.failure_step_id, "failure_step_id", max_length=128),
            )
            for name in ("failure_digest", "operation_failure_receipt_digest"):
                value = getattr(self, name)
                if value is None and name == "operation_failure_receipt_digest":
                    continue
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(ch not in "0123456789abcdef" for ch in value)
                ):
                    raise ValueError(f"{name} must be lowercase sha256")

    def as_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "status": self.status,
            "completed": [
                {"step_id": step_id, "receipt_digest": receipt_digest}
                for step_id, receipt_digest in self.completed
            ],
            "failure_step_id": self.failure_step_id,
            "failure_digest": self.failure_digest,
            "operation_failure_receipt_digest": (
                self.operation_failure_receipt_digest
            ),
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class DeferredPlanOutcome:
    receipt: DeferredPlanReceipt
    results: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, DeferredPlanReceipt):
            raise TypeError("receipt must be DeferredPlanReceipt")
        if self.receipt.status != "succeeded":
            raise ValueError("plan outcome requires succeeded receipt")
        if not isinstance(self.results, Mapping):
            raise TypeError("results must be a mapping")
        copied = json.loads(canonical_json(dict(self.results)))
        if set(copied) != {step_id for step_id, _ in self.receipt.completed}:
            raise ValueError("plan results must match completed step ids")
        object.__setattr__(self, "results", copied)


class DeferredPlanExecutionError(RuntimeError):
    def __init__(self, receipt: DeferredPlanReceipt) -> None:
        super().__init__("deferred execution plan failed")
        self.receipt = receipt


class DeferredPlanExecutor:
    def __init__(self, executor: DeferredExecutor) -> None:
        if not isinstance(executor, DeferredExecutor):
            raise TypeError("executor must be DeferredExecutor")
        self.executor = executor

    @staticmethod
    def _failure_digest(exc: BaseException) -> str:
        return sha256_json(
            {
                "type": type(exc).__name__,
                "message_digest": hashlib.sha256(
                    str(exc).encode("utf-8")
                ).hexdigest(),
            }
        )

    def execute(self, plan: DeferredPlan) -> DeferredPlanOutcome:
        if not isinstance(plan, DeferredPlan):
            raise TypeError("plan must be DeferredPlan")

        completed: list[tuple[str, str]] = []
        results: dict[str, Any] = {}

        for step in plan.ordered_steps():
            payload = step.payload()
            try:
                invocation = self.executor.prepare(
                    step.volume_id,
                    step.operation_id,
                    payload,
                    cost_units=step.cost_units,
                    latency_ms=step.latency_ms,
                )
                outcome: ExecutionOutcome = self.executor.execute(
                    invocation,
                    payload,
                )
            except Exception as exc:
                operation_receipt_digest = None
                if isinstance(exc, DeferredExecutionError):
                    operation_receipt_digest = exc.receipt.digest
                receipt = DeferredPlanReceipt(
                    plan_id=plan.plan_id,
                    plan_digest=plan.digest,
                    status="failed",
                    completed=tuple(completed),
                    failure_step_id=step.step_id,
                    failure_digest=self._failure_digest(exc),
                    operation_failure_receipt_digest=operation_receipt_digest,
                )
                raise DeferredPlanExecutionError(receipt) from exc

            completed.append((step.step_id, outcome.receipt.digest))
            results[step.step_id] = outcome.result

        receipt = DeferredPlanReceipt(
            plan_id=plan.plan_id,
            plan_digest=plan.digest,
            status="succeeded",
            completed=tuple(completed),
        )
        return DeferredPlanOutcome(receipt=receipt, results=results)
