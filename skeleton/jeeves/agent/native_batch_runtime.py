"""Deterministic operator-approved batch execution on the canonical native spine.

Every task uses one stable principal-bound session and request identity. A
cold rerun of the SAME approved batch returns the same previously committed
SQLite model answer, without a new generation. If the original native
request was pending or its effect uncertain, the existing spine refuses
retry. No hosted backend, model-authored tool grant, alternate SQLite owner,
source bypass, or speculative batch refund is introduced.

This component is not an automated code writer and does not claim 1000
physical simultaneous workers. It is a deterministic, resource-admitted
native task conveyor for the operator's existing approved local GGUF.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import time
from typing import Any, Callable, Sequence

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Conflict,
)
from .native_chat import NativeJeevesChat


class NativeBatchHold(ValueError):
    """Batch was not approved, or exactly-once native custody cannot be proved."""


def _id(value: object, label: str) -> str:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identifier
    if type(value) is not str:
        raise NativeBatchHold("explicit typed " + label + " required")
    try:
        return identifier(value, label)
    except ValueError as exc:
        raise NativeBatchHold("invalid " + label) from exc


def _text(value: object, *, maximum_bytes: int = 32768) -> str:
    if type(value) is not str or not value.strip():
        raise NativeBatchHold("nonempty UTF-8 batch task required")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise NativeBatchHold("invalid batch task Unicode") from exc
    if len(raw) > maximum_bytes or b"\x00" in raw:
        raise NativeBatchHold("batch task text exceeds admission")
    return value


@dataclass(frozen=True, slots=True)
class NativeBatchTask:
    task_id: str
    prompt: str
    exact_output_sha256: str | None = None

    def __post_init__(self):
        _id(self.task_id, "task ID")
        _text(self.prompt)
        if self.exact_output_sha256 is not None:
            from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identity_hash
            identity_hash(self.exact_output_sha256)

    @property
    def prompt_sha256(self) -> str:
        return sha256(self.prompt.encode("utf-8", "strict")).hexdigest()


@dataclass(frozen=True, slots=True)
class NativeBatchPolicy:
    maximum_jobs: int = 64
    maximum_prompt_bytes: int = 262144
    maximum_reserved_output_tokens: int = 65536
    maximum_wall_seconds: float = 1800
    maximum_single_job_ms: int = 300000
    abort_on_failed_exact_predicate: bool = True

    def __post_init__(self):
        for name, minimum, maximum in (
            ("maximum_jobs", 1, 1000),
            ("maximum_prompt_bytes", 1, 1048576),
            ("maximum_reserved_output_tokens", 1, 8192000),
            ("maximum_single_job_ms", 1, 600000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise NativeBatchHold("batch resource ceiling invalid")
        if (type(self.maximum_wall_seconds) not in (int, float)
            or not math.isfinite(self.maximum_wall_seconds)
            or not 0 < self.maximum_wall_seconds <= 86400):
            raise NativeBatchHold("invalid finite batch wall-time budget")
        if type(self.abort_on_failed_exact_predicate) is not bool:
            raise NativeBatchHold("batch objective policy requires strict boolean")


@dataclass(frozen=True, slots=True)
class NativeBatchReceipt:
    task_id: str
    session_id: str
    request_id: str
    prompt_sha256: str
    output_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    generated_tokens: int
    prompt_tokens: int
    answer_bytes: int
    replayed: bool
    duration_ms: int
    exact_objective_passed: bool | None

    def to_public_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_batch_receipt.v1",
            "task_id": self.task_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "prompt_sha256": self.prompt_sha256,
            "output_sha256": self.output_sha256,
            "model_sha256": self.model_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "generated_tokens": self.generated_tokens,
            "prompt_tokens": self.prompt_tokens,
            "answer_bytes": self.answer_bytes,
            "replayed": self.replayed,
            "duration_ms": self.duration_ms,
            "exact_objective_passed": self.exact_objective_passed,
            "native_device_qualified": False,
            "release_certified": False,
        }


@dataclass(frozen=True, slots=True)
class NativeBatchResult:
    batch_id: str
    batch_sha256: str
    receipts: tuple[NativeBatchReceipt, ...]
    committed: int
    replayed: int
    device_qualified: bool = False

    def to_public_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_batch_result.v1",
            "batch_id": self.batch_id,
            "batch_sha256": self.batch_sha256,
            "receipts": [item.to_public_record() for item in self.receipts],
            "committed_jobs": self.committed,
            "replayed_jobs": self.replayed,
            "total_jobs": len(self.receipts),
            "all_receipts_issued_by_canonical_spine": True,
            "device_qualified": False,
            "release_certified": False,
        }


def batch_identity(batch_id: str, tasks: Sequence[NativeBatchTask], *,
                   tenant: str, subject: str,
                   model_sha256: str, tokenizer_sha256: str) -> str:
    _id(batch_id, "batch")
    _id(tenant, "tenant")
    _id(subject, "subject")
    if type(tasks) not in (list, tuple):
        raise NativeBatchHold("typed batch tasks required")
    if len(tasks) > 1000:
        raise NativeBatchHold("unbounded batch digest input")
    payload = {
        "schema": "jeeves.native_batch_identity.v1",
        "batch": batch_id,
        "principal": (tenant, subject, model_sha256, tokenizer_sha256),
        "tasks": [(t.task_id, t.prompt_sha256, t.exact_output_sha256)
                  for t in tasks],
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def preflight_batch_tasks(
    batch_id: str, tasks: Sequence[NativeBatchTask],
    policy: NativeBatchPolicy, *,
    configured_output_tokens: int,
) -> dict[str, int | str]:
    """Pure operator admission BEFORE loading model packages or prompts."""
    _id(batch_id, "batch ID")
    if not isinstance(policy, NativeBatchPolicy):
        raise NativeBatchHold("typed operator batch policy required")
    if type(configured_output_tokens) is not int or not 1 <= configured_output_tokens <= 8192:
        raise NativeBatchHold("bounded configured output ceiling required")
    if type(tasks) not in (tuple, list) or not 1 <= len(tasks) <= policy.maximum_jobs:
        raise NativeBatchHold("finite operator batch casebook required")
    if any(not isinstance(task, NativeBatchTask) for task in tasks):
        raise NativeBatchHold("untyped operator job")
    if len({task.task_id for task in tasks}) != len(tasks):
        raise NativeBatchHold("ambiguous duplicate operator task ID")
    byte_total = sum(len(task.prompt.encode("utf-8", "strict")) for task in tasks)
    reservation = len(tasks) * configured_output_tokens
    if byte_total > policy.maximum_prompt_bytes:
        raise NativeBatchHold("aggregate task input bytes exceed ceiling")
    if reservation > policy.maximum_reserved_output_tokens:
        raise NativeBatchHold("native output reservation exceeds operator limit")
    return {
        "schema": "jeeves.native_batch_preflight.v1",
        "batch_id": batch_id,
        "jobs": len(tasks),
        "input_bytes": byte_total,
        "reserved_output_tokens": reservation,
    }


class NativeBatchConveyor:
    """Serial bounded worker admission with authoritative SQLite replay."""

    def __init__(
        self, worker: Any, *, approved: bool,
        policy: NativeBatchPolicy | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if approved is not True:
            raise NativeBatchHold("operator native batch approval required")
        self.identity = ActiveModel.from_supervisor(worker)
        self.worker = worker
        self.policy = policy or NativeBatchPolicy()
        if not isinstance(self.policy, NativeBatchPolicy):
            raise NativeBatchHold("typed batch policy required")
        if not callable(monotonic):
            raise NativeBatchHold("monotonic clock required")
        self.monotonic = monotonic

    def _check(self, batch_id: str, tasks: Sequence[NativeBatchTask]) -> tuple:
        _id(batch_id, "batch ID")
        if type(tasks) not in (tuple, list) or not 1 <= len(tasks) <= self.policy.maximum_jobs:
            raise NativeBatchHold("bounded operator batch required")
        if any(not isinstance(t, NativeBatchTask) for t in tasks):
            raise NativeBatchHold("typed task inventory required")
        if len({t.task_id for t in tasks}) != len(tasks):
            raise NativeBatchHold("duplicate batch task identity")
        if sum(len(t.prompt.encode("utf-8", "strict")) for t in tasks) > self.policy.maximum_prompt_bytes:
            raise NativeBatchHold("aggregate private task bytes exceed capacity")
        reservation = self.worker.spine.limits.max_output_tokens * len(tasks)
        if reservation > self.policy.maximum_reserved_output_tokens:
            raise NativeBatchHold("full native output reservation exceeds batch ceiling")
        active = ActiveModel.from_supervisor(self.worker)
        if active != self.identity:
            raise NativeBatchHold("native principal changed after batch admission")
        return tuple(tasks), batch_identity(
            batch_id, tasks,
            tenant=self.identity.tenant, subject=self.identity.subject,
            model_sha256=self.identity.model_sha256,
            tokenizer_sha256=self.identity.tokenizer_sha256,
        )

    def preflight(self, batch_id: str, tasks: Sequence[NativeBatchTask]) -> dict[str, object]:
        tasks, digest = self._check(batch_id, tasks)
        return {
            "schema": "jeeves.native_batch_admission.v1",
            "batch_id": batch_id,
            "batch_sha256": digest,
            "jobs": len(tasks),
            "reserved_output_tokens": self.worker.spine.limits.max_output_tokens * len(tasks),
            "prompt_bytes": sum(len(t.prompt.encode("utf-8")) for t in tasks),
            "operator_approval_required": True,
            "real_native_calls_started": False,
            "device_qualified": False,
        }

    def _session_key(self, batch_id: str, task_id: str) -> tuple[str, str]:
        # Session IDs do NOT depend on task content: a changed task under
        # the same ID must hit the existing SQLite request digest collision,
        # not hide by silently allocating a fresh inference identity.
        payload = json.dumps({
            "schema": "jeeves.native_batch_request_key.v1",
            "batch": batch_id, "task": task_id,
            "tenant": self.identity.tenant,
            "subject": self.identity.subject,
            "model": self.identity.model_sha256,
            "tokenizer": self.identity.tokenizer_sha256,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = sha256(payload).hexdigest()
        return "nb_" + digest[:32], "nr_" + digest[32:]

    def _conversation(self, session_id: str) -> NativeJeevesChat:
        try:
            self.worker.spine.create(session_id)
        except Conflict:
            # Owner/model-bound history independently fences foreign sessions.
            self.worker.spine.history(session_id)
        return NativeJeevesChat(self.worker, session_id=session_id)

    def run(
        self, batch_id: str, tasks: Sequence[NativeBatchTask],
    ) -> NativeBatchResult:
        tasks, batch_sha = self._check(batch_id, tasks)
        started = self.monotonic()
        results = []
        for task in tasks:
            if self.monotonic() - started >= self.policy.maximum_wall_seconds:
                raise NativeBatchHold("batch wall-clock budget exhausted")
            session, request = self._session_key(batch_id, task.task_id)
            chat = self._conversation(session)
            began = self.monotonic()
            turn = chat.turn(task.prompt, request_id=request)
            elapsed = self.monotonic() - began
            if not math.isfinite(elapsed) or elapsed < 0:
                raise NativeBatchHold("nonmonotonic native batch measurement")
            millis = int(math.ceil(elapsed * 1000))
            if millis > self.policy.maximum_single_job_ms:
                raise NativeBatchHold("single native task exceeded operator bound")
            if (turn.session_id != session or turn.request_id != request
                or turn.model_sha256 != self.identity.model_sha256
                or turn.tokenizer_sha256 != self.identity.tokenizer_sha256
                or sha256(turn.text.encode("utf-8", "strict")).hexdigest() != turn.output_sha256):
                raise NativeBatchHold("native receipt diverges from principal-bound session")
            exact = (
                turn.output_sha256 == task.exact_output_sha256
                if task.exact_output_sha256 is not None else None
            )
            receipt = NativeBatchReceipt(
                task_id=task.task_id, session_id=session,
                request_id=request, prompt_sha256=task.prompt_sha256,
                output_sha256=turn.output_sha256,
                model_sha256=turn.model_sha256,
                tokenizer_sha256=turn.tokenizer_sha256,
                generated_tokens=turn.generated_tokens,
                prompt_tokens=turn.prompt_tokens,
                answer_bytes=len(turn.text.encode("utf-8", "strict")),
                replayed=turn.replayed,
                duration_ms=millis,
                exact_objective_passed=exact,
            )
            results.append(receipt)
            if exact is False and self.policy.abort_on_failed_exact_predicate:
                # A failed quality predicate does not mean the generation
                # wasn't committed. The caller must reconcile before retry.
                raise NativeBatchHold("batch model output failed approved objective")
        return NativeBatchResult(
            batch_id=batch_id, batch_sha256=batch_sha,
            receipts=tuple(results),
            committed=sum(not x.replayed for x in results),
            replayed=sum(x.replayed for x in results),
        )


__all__ = [
    "NativeBatchHold", "NativeBatchTask", "NativeBatchPolicy",
    "NativeBatchReceipt", "NativeBatchResult", "batch_identity",
    "NativeBatchConveyor", "preflight_batch_tasks",
]
