"""Fail-closed, canonical restore of the native LLM admission scheduler.

The scheduler snapshot digest detects accidental mutation; it is NOT an
authenticity proof. Trusted callers must pin the expected digest, policy and
sequence floor when recovering state from an external store. This parser never
coerces data types, creates model execution authority or reads from a network.
"""
from __future__ import annotations

import hmac
from typing import Any

from .admission_scheduler import (
    AdmissionLimits, RuntimeAdmissionScheduler, ScheduledRequest, _digest,
)
from .flgb_model_runtime import BatchRequest, KVCacheEntry, ModelRuntimeError
from .runtime_policy import RuntimePolicy


_SNAPSHOT_FIELDS = frozenset({
    "schema", "limits", "sequence", "policy", "capacity", "queued", "active", "kv",
    "digest",
})
_LIMIT_FIELDS = frozenset({
    "max_active_requests", "max_queued_requests", "max_batch_size",
    "max_tokens_per_batch", "kv_capacity_bytes", "max_age_boost",
})
_REQUEST_FIELDS = frozenset({
    "request_id", "prompt_tokens", "max_new_tokens", "priority",
    "kv_bytes", "enqueue_sequence", "pinned_kv",
})
_KV_FIELDS = frozenset({
    "request_id", "bytes", "last_used_sequence", "pinned",
})
_POLICY_FIELDS = frozenset({
    "through_year", "capabilities", "experimental", "digest",
})
_CAPACITY_FIELDS = frozenset({
    "queued_requests", "active_requests", "active_slots_free", "queued_tokens",
    "active_tokens", "kv_used_bytes", "kv_free_bytes",
})


def _exact_fields(value: object, names: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != names:
        raise ModelRuntimeError(f"invalid {label} checkpoint fields")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ModelRuntimeError(f"invalid {label} checkpoint integer")
    return value


def _string(value: object, label: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 256:
        raise ModelRuntimeError(f"invalid {label} checkpoint string")
    return value


def _digest_string(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        ch not in "0123456789abcdef" for ch in value
    ):
        raise ModelRuntimeError(f"invalid {label} checkpoint digest")
    return value


def _policy_record(value: object) -> RuntimePolicy | None:
    if value is None:
        return None
    raw = _exact_fields(value, _POLICY_FIELDS, "policy")
    year = _integer(raw["through_year"], "policy year", minimum=1)
    digest = _digest_string(raw["digest"], "policy")
    sets: list[tuple[str, ...]] = []
    for field in ("capabilities", "experimental"):
        items = raw[field]
        if type(items) is not list or len(items) > 4096:
            raise ModelRuntimeError(f"invalid policy {field} checkpoint")
        values = tuple(_string(item, field) for item in items)
        if len(set(values)) != len(values):
            raise ModelRuntimeError(f"duplicate policy {field} checkpoint")
        sets.append(values)
    if set(sets[0]) & set(sets[1]):
        raise ModelRuntimeError("production and experimental policy overlap")
    return RuntimePolicy(year, sets[0], sets[1], digest)


def _request_record(value: object, label: str, sequence: int) -> ScheduledRequest:
    raw = _exact_fields(value, _REQUEST_FIELDS, label)
    request_id = _string(raw["request_id"], f"{label} identity")
    prompt = _integer(raw["prompt_tokens"], f"{label} prompt tokens")
    output = _integer(raw["max_new_tokens"], f"{label} output tokens")
    priority = _integer(raw["priority"], f"{label} priority", minimum=-1_000_000)
    kv_bytes = _integer(raw["kv_bytes"], f"{label} KV bytes", minimum=1)
    enqueue = _integer(raw["enqueue_sequence"], f"{label} enqueue sequence")
    if enqueue >= sequence:
        raise ModelRuntimeError(f"{label} enqueue sequence lies in the future")
    pinned = raw["pinned_kv"]
    if type(pinned) is not bool:
        raise ModelRuntimeError(f"invalid {label} pinned KV flag")
    return ScheduledRequest(
        BatchRequest(request_id, prompt, output, priority),
        kv_bytes, enqueue, pinned,
    )


def _kv_record(value: object, sequence: int) -> KVCacheEntry:
    raw = _exact_fields(value, _KV_FIELDS, "KV entry")
    entry_sequence = _integer(raw["last_used_sequence"], "KV last-used")
    if entry_sequence >= sequence:
        raise ModelRuntimeError("KV last-used sequence lies in the future")
    if type(raw["pinned"]) is not bool:
        raise ModelRuntimeError("invalid KV pinned flag")
    return KVCacheEntry(
        _string(raw["request_id"], "KV identity"),
        _integer(raw["bytes"], "KV bytes", minimum=1),
        entry_sequence,
        raw["pinned"],
    )


def restore_admission_scheduler(
    snapshot: dict[str, object], *,
    expected_policy: RuntimePolicy | None = None,
    expected_limits: AdmissionLimits | None = None,
    minimum_sequence: int | None = None,
    expected_digest: str | None = None,
) -> RuntimeAdmissionScheduler:
    """Validate and restore one deterministic admission scheduler state.

    Optional pins are supplied from a trusted, independent authority:
    `expected_policy` and `expected_limits` bind deployment configuration,
    `expected_digest` pins an exact persisted revision, and
    `minimum_sequence` rejects rollback below a durable monotonic floor.
    An omitted pin does not imply external source authenticity.
    """
    raw = _exact_fields(snapshot, _SNAPSHOT_FIELDS, "scheduler")
    if raw["schema"] != "skeleton.ai.runtime-admission-scheduler.v1":
        raise ModelRuntimeError("invalid admission scheduler snapshot schema")
    supplied_digest = _digest_string(raw["digest"], "scheduler")
    if expected_digest is not None:
        pinned = _digest_string(expected_digest, "expected scheduler")
        if not hmac.compare_digest(supplied_digest, pinned):
            raise ModelRuntimeError("admission scheduler does not match expected digest")
    if minimum_sequence is not None:
        _integer(minimum_sequence, "minimum sequence")
    if expected_policy is not None and not isinstance(expected_policy, RuntimePolicy):
        raise ModelRuntimeError("RuntimePolicy required for expected policy")
    if expected_limits is not None and not isinstance(expected_limits, AdmissionLimits):
        raise ModelRuntimeError("AdmissionLimits required for expected limits")
    unsigned = {key: value for key, value in raw.items() if key != "digest"}
    try:
        calculated = _digest(unsigned)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ModelRuntimeError("invalid admission scheduler checkpoint encoding") from exc
    if not hmac.compare_digest(calculated, supplied_digest):
        raise ModelRuntimeError("admission scheduler snapshot digest mismatch")

    raw_limits = _exact_fields(raw["limits"], _LIMIT_FIELDS, "scheduler limits")
    limits = AdmissionLimits(**{
        name: _integer(raw_limits[name], f"scheduler limit {name}", minimum=1)
        for name in _LIMIT_FIELDS
    })
    sequence = _integer(raw["sequence"], "scheduler sequence")
    if minimum_sequence is not None and sequence < minimum_sequence:
        raise ModelRuntimeError("scheduler checkpoint violates minimum sequence")
    policy = _policy_record(raw["policy"])
    if expected_policy is not None and policy != expected_policy:
        raise ModelRuntimeError("scheduler checkpoint policy mismatch")
    if expected_limits is not None and limits != expected_limits:
        raise ModelRuntimeError("scheduler checkpoint limits mismatch")

    def parse_requests(value: object, label: str, maximum: int) -> dict[str, ScheduledRequest]:
        if type(value) is not list or len(value) > maximum:
            raise ModelRuntimeError(f"invalid {label} scheduler checkpoint")
        result: dict[str, ScheduledRequest] = {}
        used_sequences: set[int] = set()
        for raw_item in value:
            item = _request_record(raw_item, label, sequence)
            request_id = item.request.request_id
            if request_id in result:
                raise ModelRuntimeError("duplicate scheduler request identity in snapshot")
            if item.enqueue_sequence in used_sequences:
                raise ModelRuntimeError("duplicate scheduler enqueue sequence")
            if item.kv_bytes > limits.kv_capacity_bytes:
                raise ModelRuntimeError("scheduler item exceeds KV capacity")
            if item.request.prompt_tokens + item.request.max_new_tokens > limits.max_tokens_per_batch:
                raise ModelRuntimeError("scheduler item exceeds token capacity")
            result[request_id] = item
            used_sequences.add(item.enqueue_sequence)
        return result

    queued = parse_requests(raw["queued"], "queued", limits.max_queued_requests)
    active = parse_requests(raw["active"], "active", limits.max_active_requests)
    if set(queued) & set(active):
        raise ModelRuntimeError("request cannot be queued and active in snapshot")
    if {item.enqueue_sequence for item in queued.values()} & {
        item.enqueue_sequence for item in active.values()
    }:
        raise ModelRuntimeError("duplicate request enqueue sequence across states")

    raw_kv = raw["kv"]
    # All KV entries hold at least one physical byte. Bound the record count
    # before constructing any instances, including retained completed entries.
    if type(raw_kv) is not list or len(raw_kv) > min(limits.kv_capacity_bytes, 65_536):
        raise ModelRuntimeError("invalid KV scheduler checkpoint size")
    kv: dict[str, KVCacheEntry] = {}
    resident_bytes = 0
    for raw_item in raw_kv:
        entry = _kv_record(raw_item, sequence)
        if entry.request_id in kv:
            raise ModelRuntimeError("duplicate KV identity in snapshot")
        resident_bytes += entry.bytes
        if resident_bytes > limits.kv_capacity_bytes:
            raise ModelRuntimeError("scheduler snapshot exceeds KV capacity")
        kv[entry.request_id] = entry

    if not set(active).issubset(kv):
        raise ModelRuntimeError("active request missing KV state")
    if set(queued) & set(kv):
        raise ModelRuntimeError("queued request reuses resident KV identity")
    for request_id, item in active.items():
        entry = kv[request_id]
        if entry.bytes != item.kv_bytes or entry.pinned != item.pinned_kv:
            raise ModelRuntimeError("active request/KV checkpoint mismatch")
        if entry.last_used_sequence < item.enqueue_sequence:
            raise ModelRuntimeError("active request KV chronology mismatch")

    raw_capacity = _exact_fields(raw["capacity"], _CAPACITY_FIELDS, "scheduler capacity")
    for name in _CAPACITY_FIELDS:
        _integer(raw_capacity[name], f"scheduler capacity {name}")

    scheduler = RuntimeAdmissionScheduler(limits, policy=policy)
    scheduler._queued = queued
    scheduler._active = active
    scheduler._kv = kv
    scheduler._sequence = sequence
    if scheduler.capacity() != raw_capacity:
        raise ModelRuntimeError("scheduler snapshot capacity mismatch")
    # Canonical round-trip prohibits identity/ordering changes after restore,
    # including matching digests over noncanonical collections.
    if scheduler.snapshot() != snapshot:
        raise ModelRuntimeError("noncanonical scheduler checkpoint")
    return scheduler


__all__ = ["restore_admission_scheduler"]
