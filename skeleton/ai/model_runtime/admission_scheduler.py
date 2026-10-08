"""Deterministic admission and scheduling control plane for local model serving."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .flgb_model_runtime import BatchRequest, KVCacheEntry, ModelRuntimeError, plan_kv_admission
from .runtime_policy import RuntimePolicy


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _require_request_id(value: object) -> str:
    """Reject malformed public operation identifiers before state lookup."""
    if type(value) is not str or not 1 <= len(value) <= 256:
        raise ModelRuntimeError("invalid scheduler request identity")
    return value


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
    kv_evicted_bytes: int
    resident_kv_bytes: int
    snapshot_digest: str


class RuntimeAdmissionScheduler:
    """Stateful, deterministic and fail-closed local inference admission scheduler."""

    def __init__(self, limits: AdmissionLimits | None = None, *, policy: RuntimePolicy | None = None) -> None:
        if limits is not None and not isinstance(limits, AdmissionLimits):
            raise ModelRuntimeError("AdmissionLimits required")
        self.limits = limits if limits is not None else AdmissionLimits()
        if policy is not None and not isinstance(policy, RuntimePolicy):
            raise ModelRuntimeError("RuntimePolicy required")
        self.policy = policy
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
        if not isinstance(request, BatchRequest):
            raise ModelRuntimeError("BatchRequest required")
        # A completed request may retain KV data. Reusing that identity before
        # explicit eviction would collide with resident-cache ownership during
        # admission; reject it at submission rather than dropping queued work.
        if (request.request_id in self._queued or request.request_id in self._active
                or request.request_id in self._kv):
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
        kv_evicted_bytes = 0

        working_kv = list(self._kv.values())
        for item in self._ordered_queue():
            rid = item.request.request_id
            demand = item.request.prompt_tokens + item.request.max_new_tokens
            if len(admitted) >= batch_slots or token_demand + demand > token_budget:
                deferred.append(rid)
                continue
            incoming = KVCacheEntry(rid, item.kv_bytes, self._sequence, item.pinned_kv)
            # Active decode state is resident by definition. Treat it as pinned
            # during planning even if the retained-cache pin flag is false.
            planning_kv = [
                KVCacheEntry(
                    entry.request_id, entry.bytes, entry.last_used_sequence,
                    entry.pinned or entry.request_id in self._active,
                )
                for entry in working_kv
            ]
            try:
                victims, ok = plan_kv_admission(
                    planning_kv, incoming, capacity_bytes=self.limits.kv_capacity_bytes
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
            kv_evicted_bytes += sum(entry.bytes for entry in working_kv if entry.request_id in victim_set)
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
            token_demand, kv_demand, kv_evicted_bytes,
            sum(entry.bytes for entry in self._kv.values()), _digest(payload)
        )

    def cancel(self, request_id: str) -> str:
        """Withdraw queued work or terminate active work and release its KV state."""
        _require_request_id(request_id)
        if request_id in self._queued:
            self._queued.pop(request_id)
            self._sequence += 1
            return "queued"
        if request_id in self._active:
            self._active.pop(request_id)
            self._kv.pop(request_id, None)
            self._sequence += 1
            return "active"
        raise ModelRuntimeError("cannot cancel unknown request")

    def retry(self, request_id: str, *, priority_delta: int = 0) -> None:
        """Move active work back to the queue with a fresh sequence and no stale KV."""
        _require_request_id(request_id)
        item = self._active.get(request_id)
        if item is None:
            raise ModelRuntimeError("cannot retry inactive request")
        if isinstance(priority_delta, bool) or not isinstance(priority_delta, int):
            raise ModelRuntimeError("priority_delta must be integer")
        priority = item.request.priority + priority_delta
        if not -1_000_000 <= priority <= 1_000_000:
            raise ModelRuntimeError("retry priority outside supported range")
        # Preserve the active request and its resident KV on admission failure:
        # a retry may be attempted while every waiting slot is occupied.
        if len(self._queued) >= self.limits.max_queued_requests:
            raise ModelRuntimeError("runtime admission retry queue capacity exceeded")
        request = BatchRequest(request_id, item.request.prompt_tokens, item.request.max_new_tokens, priority)
        replacement = ScheduledRequest(
            request, item.kv_bytes, self._sequence, item.pinned_kv
        )
        self._active.pop(request_id)
        self._kv.pop(request_id, None)
        self._queued[request_id] = replacement
        self._sequence += 1

    def set_kv_pinned(self, request_id: str, pinned: bool) -> None:
        _require_request_id(request_id)
        if not isinstance(pinned, bool):
            raise ModelRuntimeError("pinned must be boolean")
        entry = self._kv.get(request_id)
        if entry is None:
            raise ModelRuntimeError("KV entry not found")
        self._kv[request_id] = KVCacheEntry(entry.request_id, entry.bytes, self._sequence, pinned)
        active = self._active.get(request_id)
        if active is not None:
            self._active[request_id] = ScheduledRequest(active.request, active.kv_bytes, active.enqueue_sequence, pinned)
        self._sequence += 1

    def capacity(self) -> dict[str, int]:
        kv_used = sum(entry.bytes for entry in self._kv.values())
        queued_tokens = sum(item.request.prompt_tokens + item.request.max_new_tokens for item in self._queued.values())
        active_tokens = sum(item.request.prompt_tokens + item.request.max_new_tokens for item in self._active.values())
        return {
            "queued_requests": len(self._queued),
            "active_requests": len(self._active),
            "active_slots_free": self.limits.max_active_requests - len(self._active),
            "queued_tokens": queued_tokens,
            "active_tokens": active_tokens,
            "kv_used_bytes": kv_used,
            "kv_free_bytes": self.limits.kv_capacity_bytes - kv_used,
        }

    def complete(self, request_id: str, *, retain_kv: bool = False) -> None:
        _require_request_id(request_id)
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
        body: dict[str, object] = {
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
            "policy": None if self.policy is None else {
                "through_year": self.policy.through_year,
                "capabilities": list(self.policy.capabilities),
                "experimental": list(self.policy.experimental),
                "digest": self.policy.digest,
            },
            "capacity": self.capacity(),
            "queued": [
                {
                    "request_id": item.request.request_id,
                    "prompt_tokens": item.request.prompt_tokens,
                    "max_new_tokens": item.request.max_new_tokens,
                    "priority": item.request.priority,
                    "kv_bytes": item.kv_bytes,
                    "enqueue_sequence": item.enqueue_sequence,
                    "pinned_kv": item.pinned_kv,
                }
                for item in sorted(self._queued.values(), key=lambda x: x.request.request_id)
            ],
            "active": [
                {
                    "request_id": item.request.request_id,
                    "prompt_tokens": item.request.prompt_tokens,
                    "max_new_tokens": item.request.max_new_tokens,
                    "priority": item.request.priority,
                    "kv_bytes": item.kv_bytes,
                    "enqueue_sequence": item.enqueue_sequence,
                    "pinned_kv": item.pinned_kv,
                }
                for item in sorted(self._active.values(), key=lambda x: x.request.request_id)
            ],
            "kv": [
                {
                    "request_id": entry.request_id,
                    "bytes": entry.bytes,
                    "last_used_sequence": entry.last_used_sequence,
                    "pinned": entry.pinned,
                }
                for entry in sorted(self._kv.values(), key=lambda x: x.request_id)
            ],
        }
        body["digest"] = _digest(body)
        return body


__all__ = [
    "AdmissionDecision",
    "AdmissionLimits",
    "RuntimeAdmissionScheduler",
    "ScheduledRequest",
]
