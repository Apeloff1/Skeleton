"""Deterministic admission and scheduling control plane for local model serving."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .flgb_model_runtime import BatchRequest, KVCacheEntry, ModelRuntimeError, plan_kv_admission


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionLimits:
    max_active_requests: int = 32
    max_queued_requests: int = 4096
    max_batch_size: int = 16
    max_tokens_per_batch: int = 32768
    kv_capacity_bytes: int = 1 << 30
    max_age_boost: int = 1000

    def __post_init__(self) -> None:
        for name in ("max_active_requests", "max_queued_requests", "max_batch_size",
                     "max_tokens_per_batch", "kv_capacity_bytes", "max_age_boost"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ModelRuntimeError(f"invalid {name}")
        if self.max_batch_size > self.max_active_requests:
            raise ModelRuntimeError("batch size cannot exceed active request limit")


@dataclass(frozen=True, slots=True)
class ScheduledRequest:
    request: BatchRequest
    kv_bytes: int
    enqueue_sequence: int
    pinned_kv: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.request, BatchRequest):
            raise ModelRuntimeError("BatchRequest required")
        if isinstance(self.kv_bytes, bool) or not isinstance(self.kv_bytes, int) or self.kv_bytes <= 0:
            raise ModelRuntimeError("positive kv_bytes required")
        if isinstance(self.enqueue_sequence, bool) or not isinstance(self.enqueue_sequence, int) or self.enqueue_sequence < 0:
            raise ModelRuntimeError("invalid enqueue sequence")
        if not isinstance(self.pinned_kv, bool):
            raise ModelRuntimeError("pinned_kv must be boolean")


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admitted: tuple[str, ...]
    deferred: tuple[str, ...]
    evicted_kv: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    token_demand: int
    kv_demand: int
    snapshot_digest: str


class RuntimeAdmissionScheduler:
    """Stateful, deterministic and fail-closed local inference admission scheduler."""

    def __init__(self, limits: AdmissionLimits | None = None) -> None:
        self.limits = limits or AdmissionLimits()
        self._queued: dict[str, ScheduledRequest] = {}
        self._active: dict[str, ScheduledRequest] = {}
        self._kv: dict[str, KVCacheEntry] = {}
        self._sequence = 0

    @property
    def queued_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._queued))

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    def submit(self, request: BatchRequest, *, kv_bytes: int, pinned_kv: bool = False) -> None:
        if request.request_id in self._queued or request.request_id in self._active:
            raise ModelRuntimeError("duplicate scheduler request identity")
        if len(self._queued) >= self.limits.max_queued_requests:
            raise ModelRuntimeError("runtime admission queue capacity exceeded")
        scheduled = ScheduledRequest(request, kv_bytes, self._sequence, pinned_kv)
        if scheduled.kv_bytes > self.limits.kv_capacity_bytes:
            raise ModelRuntimeError("request KV demand exceeds total capacity")
        if request.prompt_tokens + request.max_new_tokens > self.limits.max_tokens_per_batch:
            raise ModelRuntimeError("request token demand exceeds batch capacity")
        self._queued[request.request_id] = scheduled
        self._sequence += 1

    def _effective_priority(self, item: ScheduledRequest) -> int:
        age = max(0, self._sequence - item.enqueue_sequence)
        return item.request.priority + min(age, self.limits.max_age_boost)

    def _ordered_queue(self) -> tuple[ScheduledRequest, ...]:
        return tuple(sorted(
            self._queued.values(),
            key=lambda item: (-self._effective_priority(item), item.enqueue_sequence, item.request.request_id),
        ))

    def admit(self) -> AdmissionDecision:
        slots = self.limits.max_active_requests - len(self._active)
        batch_slots = min(slots, self.limits.max_batch_size)
        token_budget = self.limits.max_tokens_per_batch
        admitted: list[str] = []
        deferred: list[str] = []
        evicted: list[str] = []
        rejected: list[tuple[str, str]] = []
        token_demand = 0
        kv_demand = 0

        working_kv = list(self._kv.values())
        for item in self._ordered_queue():
            rid = item.request.request_id
            demand = item.request.prompt_tokens + item.request.max_new_tokens
            if len(admitted) >= batch_slots or token_demand + demand > token_budget:
                deferred.append(rid)
                continue
            incoming = KVCacheEntry(rid, item.kv_bytes, self._sequence, item.pinned_kv)
            try:
                victims, ok = plan_kv_admission(
                    working_kv, incoming, capacity_bytes=self.limits.kv_capacity_bytes
                )
            except ModelRuntimeError as exc:
                rejected.append((rid, str(exc)))
                continue
            if not ok:
                deferred.append(rid)
                continue
            victim_set = set(victims)
            if victim_set & set(self._active):
                deferred.append(rid)
                continue
            working_kv = [entry for entry in working_kv if entry.request_id not in victim_set]
            for victim in victims:
                if victim not in evicted:
                    evicted.append(victim)
            working_kv.append(incoming)
            admitted.append(rid)
            token_demand += demand
            kv_demand += item.kv_bytes

        for victim in evicted:
            self._kv.pop(victim, None)
        for rid in admitted:
            item = self._queued.pop(rid)
            self._active[rid] = item
        for rid, _reason in rejected:
            self._queued.pop(rid, None)
        self._kv = {entry.request_id: entry for entry in working_kv}
        self._sequence += 1
        payload = self.snapshot()
        return AdmissionDecision(
            tuple(admitted), tuple(deferred), tuple(evicted), tuple(rejected),
            token_demand, kv_demand, _digest(payload)
        )

    def complete(self, request_id: str, *, retain_kv: bool = False) -> None:
        if request_id not in self._active:
            raise ModelRuntimeError("cannot complete inactive request")
        self._active.pop(request_id)
        if not retain_kv:
            self._kv.pop(request_id, None)
        else:
            entry = self._kv.get(request_id)
            if entry is not None:
                self._kv[request_id] = KVCacheEntry(
                    entry.request_id, entry.bytes, self._sequence, entry.pinned
                )
        self._sequence += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "schema": "skeleton.ai.runtime-admission-scheduler.v1",
            "limits": {
                "max_active_requests": self.limits.max_active_requests,
                "max_queued_requests": self.limits.max_queued_requests,
                "max_batch_size": self.limits.max_batch_size,
                "max_tokens_per_batch": self.limits.max_tokens_per_batch,
                "kv_capacity_bytes": self.limits.kv_capacity_bytes,
                "max_age_boost": self.limits.max_age_boost,
            },
            "sequence": self._sequence,
            "queued": list(self.queued_ids),
            "active": list(self.active_ids),
            "kv": [
                {"request_id": e.request_id, "bytes": e.bytes,
                 "last_used_sequence": e.last_used_sequence, "pinned": e.pinned}
                for e in sorted(self._kv.values(), key=lambda x: x.request_id)
            ],
        }


__all__ = [
    "AdmissionDecision",
    "AdmissionLimits",
    "RuntimeAdmissionScheduler",
    "ScheduledRequest",
]
