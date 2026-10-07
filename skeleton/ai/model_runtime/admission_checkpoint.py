"""Validated persistence for runtime admission scheduler state."""
from __future__ import annotations

from .admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler, ScheduledRequest
from .flgb_model_runtime import BatchRequest, KVCacheEntry, ModelRuntimeError
from .runtime_policy import RuntimePolicy


def restore_admission_scheduler(snapshot: dict[str, object]) -> RuntimeAdmissionScheduler:
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "skeleton.ai.runtime-admission-scheduler.v1":
        raise ModelRuntimeError("invalid admission scheduler snapshot schema")
    try:
        raw_limits = snapshot["limits"]
        sequence = snapshot["sequence"]
        queued = snapshot["queued"]
        active = snapshot["active"]
        kv = snapshot["kv"]
        raw_policy = snapshot["policy"]
    except KeyError as exc:
        raise ModelRuntimeError(f"missing scheduler snapshot field: {exc.args[0]}") from exc
    if not isinstance(raw_limits, dict):
        raise ModelRuntimeError("invalid scheduler limits snapshot")
    limits = AdmissionLimits(**raw_limits)
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ModelRuntimeError("invalid scheduler snapshot sequence")

    policy = None
    if raw_policy is not None:
        if not isinstance(raw_policy, dict):
            raise ModelRuntimeError("invalid scheduler policy snapshot")
        try:
            policy = RuntimePolicy(
                int(raw_policy["through_year"]),
                tuple(raw_policy["capabilities"]),
                tuple(raw_policy["experimental"]),
                str(raw_policy["digest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelRuntimeError("invalid scheduler policy snapshot") from exc
        if len(policy.digest) != 64:
            raise ModelRuntimeError("invalid scheduler policy digest")

    scheduler = RuntimeAdmissionScheduler(limits, policy=policy)

    def parse_items(raw: object, label: str) -> dict[str, ScheduledRequest]:
        if not isinstance(raw, list):
            raise ModelRuntimeError(f"invalid {label} scheduler snapshot")
        result: dict[str, ScheduledRequest] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise ModelRuntimeError(f"invalid {label} request snapshot")
            try:
                request = BatchRequest(
                    str(item["request_id"]), int(item["prompt_tokens"]),
                    int(item["max_new_tokens"]), int(item["priority"]),
                )
                scheduled = ScheduledRequest(
                    request, int(item["kv_bytes"]), int(item["enqueue_sequence"]),
                    item["pinned_kv"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelRuntimeError(f"invalid {label} request snapshot") from exc
            if request.request_id in result:
                raise ModelRuntimeError("duplicate scheduler request identity in snapshot")
            result[request.request_id] = scheduled
        return result

    queued_items = parse_items(queued, "queued")
    active_items = parse_items(active, "active")
    if set(queued_items) & set(active_items):
        raise ModelRuntimeError("request cannot be queued and active in snapshot")
    if len(queued_items) > limits.max_queued_requests or len(active_items) > limits.max_active_requests:
        raise ModelRuntimeError("scheduler snapshot exceeds request limits")

    if not isinstance(kv, list):
        raise ModelRuntimeError("invalid KV scheduler snapshot")
    kv_items: dict[str, KVCacheEntry] = {}
    for item in kv:
        if not isinstance(item, dict):
            raise ModelRuntimeError("invalid KV entry snapshot")
        try:
            entry = KVCacheEntry(
                str(item["request_id"]), int(item["bytes"]),
                int(item["last_used_sequence"]), item["pinned"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelRuntimeError("invalid KV entry snapshot") from exc
        if entry.request_id in kv_items:
            raise ModelRuntimeError("duplicate KV identity in snapshot")
        kv_items[entry.request_id] = entry
    if sum(entry.bytes for entry in kv_items.values()) > limits.kv_capacity_bytes:
        raise ModelRuntimeError("scheduler snapshot exceeds KV capacity")
    if not set(active_items).issubset(kv_items):
        raise ModelRuntimeError("active request missing KV state")

    scheduler._queued = queued_items
    scheduler._active = active_items
    scheduler._kv = kv_items
    scheduler._sequence = sequence
    expected_capacity = snapshot.get("capacity")
    if expected_capacity is not None and expected_capacity != scheduler.capacity():
        raise ModelRuntimeError("scheduler snapshot capacity mismatch")
    return scheduler


__all__ = ["restore_admission_scheduler"]
