"""Deterministic bounded continuous-batch planning for VOL-007.

This module plans compatible request groups. It owns no provider credentials,
network transport, or result publication authority. Callers remain responsible
for executing each request through the canonical provider runtime and producing
ordinary ModelResult receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from .session import InferenceContractError, ModelRequest


MAX_BATCH_SIZE = 64
MAX_QUEUE_SIZE = 4096


def _digest(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class BatchCompatibilityKey:
    provider: str
    model: str
    max_output_tokens: int

    @classmethod
    def from_request(cls, request: ModelRequest) -> "BatchCompatibilityKey":
        if not isinstance(request, ModelRequest):
            raise InferenceContractError("ModelRequest required")
        return cls(
            provider=request.provider,
            model=request.model,
            max_output_tokens=request.max_output_tokens,
        )


@dataclass(frozen=True, slots=True)
class BatchItem:
    request: ModelRequest
    enqueued_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.request, ModelRequest):
            raise InferenceContractError("ModelRequest required")
        if (
            not isinstance(self.enqueued_ms, int)
            or isinstance(self.enqueued_ms, bool)
            or self.enqueued_ms < 0
        ):
            raise InferenceContractError("invalid enqueue timestamp")


@dataclass(frozen=True, slots=True)
class BatchPlan:
    compatibility: BatchCompatibilityKey
    operation_ids: tuple[str, ...]
    request_digests: tuple[str, ...]
    formed_at_ms: int
    authority_scope: str = "batch-plan-only"

    def __post_init__(self) -> None:
        if not isinstance(self.compatibility, BatchCompatibilityKey):
            raise InferenceContractError("BatchCompatibilityKey required")
        if not self.operation_ids or len(self.operation_ids) > MAX_BATCH_SIZE:
            raise InferenceContractError("invalid batch size")
        if len(self.operation_ids) != len(self.request_digests):
            raise InferenceContractError("batch identity cardinality mismatch")
        if len(set(self.operation_ids)) != len(self.operation_ids):
            raise InferenceContractError("duplicate operation in batch")
        if len(set(self.request_digests)) != len(self.request_digests):
            raise InferenceContractError("duplicate request digest in batch")
        if (
            not isinstance(self.formed_at_ms, int)
            or isinstance(self.formed_at_ms, bool)
            or self.formed_at_ms < 0
        ):
            raise InferenceContractError("invalid batch formation timestamp")
        if self.authority_scope != "batch-plan-only":
            raise InferenceContractError("batch plan cannot grant inference authority")

    @property
    def plan_digest(self) -> str:
        return _digest(
            {
                "compatibility": {
                    "provider": self.compatibility.provider,
                    "model": self.compatibility.model,
                    "max_output_tokens": self.compatibility.max_output_tokens,
                },
                "operation_ids": self.operation_ids,
                "request_digests": self.request_digests,
                "formed_at_ms": self.formed_at_ms,
                "authority_scope": self.authority_scope,
            }
        )


class ContinuousBatchScheduler:
    """Bounded deterministic FIFO batching by provider/model/output shape."""

    def __init__(
        self,
        *,
        max_batch_size: int = 8,
        max_queue_size: int = 256,
        max_wait_ms: int = 10,
    ) -> None:
        for name, value, hard in (
            ("max_batch_size", max_batch_size, MAX_BATCH_SIZE),
            ("max_queue_size", max_queue_size, MAX_QUEUE_SIZE),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
                or value > hard
            ):
                raise InferenceContractError(f"invalid {name}")
        if (
            not isinstance(max_wait_ms, int)
            or isinstance(max_wait_ms, bool)
            or max_wait_ms < 0
        ):
            raise InferenceContractError("invalid max_wait_ms")
        self.max_batch_size = max_batch_size
        self.max_queue_size = max_queue_size
        self.max_wait_ms = max_wait_ms
        self._queue: list[BatchItem] = []

    @property
    def queued(self) -> int:
        return len(self._queue)

    def enqueue(self, request: ModelRequest, *, enqueued_ms: int) -> None:
        if len(self._queue) >= self.max_queue_size:
            raise InferenceContractError("batch queue capacity exceeded")
        if any(item.request.operation_id == request.operation_id for item in self._queue):
            raise InferenceContractError("duplicate queued operation")
        if any(item.request.request_digest == request.request_digest for item in self._queue):
            raise InferenceContractError("duplicate queued request digest")
        self._queue.append(BatchItem(request, enqueued_ms))

    def _deadline_due(self, item: BatchItem, now_ms: int) -> bool:
        age = now_ms - item.enqueued_ms
        if age < 0:
            raise InferenceContractError("clock moved before enqueue time")
        return age >= min(self.max_wait_ms, item.request.deadline_ms)

    def drain_ready(self, *, now_ms: int) -> tuple[tuple[BatchPlan, tuple[ModelRequest, ...]], ...]:
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise InferenceContractError("invalid scheduler clock")
        if not self._queue:
            return ()

        groups: list[tuple[BatchPlan, tuple[ModelRequest, ...]]] = []
        remaining = list(self._queue)
        consumed_ids: set[str] = set()

        for item in remaining:
            if item.request.operation_id in consumed_ids:
                continue
            key = BatchCompatibilityKey.from_request(item.request)
            compatible = [
                candidate
                for candidate in remaining
                if candidate.request.operation_id not in consumed_ids
                and BatchCompatibilityKey.from_request(candidate.request) == key
            ]
            compatible.sort(
                key=lambda candidate: (
                    candidate.enqueued_ms,
                    candidate.request.operation_id,
                    candidate.request.request_digest,
                )
            )
            ready = (
                len(compatible) >= self.max_batch_size
                or self._deadline_due(compatible[0], now_ms)
            )
            if not ready:
                continue

            selected = compatible[: self.max_batch_size]
            for candidate in selected:
                consumed_ids.add(candidate.request.operation_id)
            requests = tuple(candidate.request for candidate in selected)
            plan = BatchPlan(
                compatibility=key,
                operation_ids=tuple(request.operation_id for request in requests),
                request_digests=tuple(request.request_digest for request in requests),
                formed_at_ms=now_ms,
            )
            groups.append((plan, requests))

        if consumed_ids:
            self._queue = [
                item
                for item in self._queue
                if item.request.operation_id not in consumed_ids
            ]
        return tuple(groups)

    def flush_all(self, *, now_ms: int) -> tuple[tuple[BatchPlan, tuple[ModelRequest, ...]], ...]:
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise InferenceContractError("invalid scheduler clock")
        groups: list[tuple[BatchPlan, tuple[ModelRequest, ...]]] = []
        while self._queue:
            first = min(
                self._queue,
                key=lambda item: (
                    item.enqueued_ms,
                    item.request.operation_id,
                    item.request.request_digest,
                ),
            )
            key = BatchCompatibilityKey.from_request(first.request)
            compatible = [
                item
                for item in self._queue
                if BatchCompatibilityKey.from_request(item.request) == key
            ]
            compatible.sort(
                key=lambda item: (
                    item.enqueued_ms,
                    item.request.operation_id,
                    item.request.request_digest,
                )
            )
            selected = compatible[: self.max_batch_size]
            selected_ids = {item.request.operation_id for item in selected}
            requests = tuple(item.request for item in selected)
            groups.append(
                (
                    BatchPlan(
                        compatibility=key,
                        operation_ids=tuple(request.operation_id for request in requests),
                        request_digests=tuple(request.request_digest for request in requests),
                        formed_at_ms=now_ms,
                    ),
                    requests,
                )
            )
            self._queue = [
                item
                for item in self._queue
                if item.request.operation_id not in selected_ids
            ]
        return tuple(groups)


def verify_batch_membership(
    plan: BatchPlan,
    requests: Iterable[ModelRequest],
) -> bool:
    if not isinstance(plan, BatchPlan):
        raise InferenceContractError("BatchPlan required")
    normalized = tuple(requests)
    if any(not isinstance(request, ModelRequest) for request in normalized):
        raise InferenceContractError("ModelRequest required")
    if tuple(request.operation_id for request in normalized) != plan.operation_ids:
        raise InferenceContractError("batch operation identity mismatch")
    if tuple(request.request_digest for request in normalized) != plan.request_digests:
        raise InferenceContractError("batch request identity mismatch")
    if any(
        BatchCompatibilityKey.from_request(request) != plan.compatibility
        for request in normalized
    ):
        raise InferenceContractError("batch compatibility mismatch")
    return True
