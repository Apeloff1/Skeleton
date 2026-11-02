"""Cooperative CPU+RAM+KV custody bundle for guarded offline inference.

No result from this module grants execution, memory allocation, or GPU access.
It joins three independently fail-closed observers/guards and rolls back
partial reservations. Backends MUST independently authorize and revalidate.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from secrets import token_hex
from threading import Lock
from typing import Callable

from .long_context_cpu_guard import CpuCapacityRequest
from .long_context_kv_compatibility import KvLayout, KvWindowRequest
from .long_context_memory_budget import MemoryBudgetRequest
from .long_context_spool import LongContextSpoolError, _digest

_SCHEMA = "skeleton.ai.long-context-admission-bundle.v1"
_MAX_ACTIVE = 64


@dataclass(frozen=True, slots=True)
class AdmissionBundleRequest:
    cpu: CpuCapacityRequest
    memory: MemoryBudgetRequest
    kv_layout: KvLayout
    kv_window: KvWindowRequest
    expected_model_digest: str

    def __post_init__(self) -> None:
        if (not isinstance(self.cpu, CpuCapacityRequest)
                or not isinstance(self.memory, MemoryBudgetRequest)
                or not isinstance(self.kv_layout, KvLayout)
                or not isinstance(self.kv_window, KvWindowRequest)):
            raise LongContextSpoolError("invalid admission bundle request")
        _digest(self.expected_model_digest, "expected model")
        if (self.cpu.principal != self.memory.principal
                or self.cpu.stream_id != self.memory.stream_id
                or self.cpu.stream_id != self.kv_window.stream_id
                or self.cpu.checkpoint_digest != self.kv_window.checkpoint_digest
                or self.cpu.generation != self.kv_window.generation
                or self.cpu.max_tokens != self.kv_window.max_tokens
                or self.cpu.tokenizer_digest != self.kv_layout.tokenizer_digest
                or self.expected_model_digest != self.kv_layout.model_digest
                or self.kv_layout.device_kind != "cpu"):
            raise LongContextSpoolError("admission bundle identity mismatch")


@dataclass(slots=True)
class _Bundle:
    request: AdmissionBundleRequest
    memory_id: str
    cpu_id: str
    window_digest: str
    state: str = "reserved"


class LongContextAdmissionBundle:
    """Absent -> reserved -> claimed -> released/revoked; never execution.

    Caller owns verified CPU/memory guards and KV progress observer. This
    process-local coordinator cannot provide cross-process atomic admission.
    The guards must independently validate principal, live pressure, RAM,
    checkpoint, tokenizer, and disk at both reservation and claim.
    """

    def __init__(self, cpu_guard: object, memory_guard: object,
                 kv_observer: object, *, max_active: int = 8,
                 nonce: Callable[[int], str] = token_hex) -> None:
        if type(max_active) is not int or not 1 <= max_active <= _MAX_ACTIVE:
            raise LongContextSpoolError("invalid admission bundle limit")
        if not callable(nonce):
            raise LongContextSpoolError("invalid admission bundle nonce")
        for guard, names in (
            (cpu_guard, ("reserve", "claim", "release")),
            (memory_guard, ("reserve", "claim", "release")),
            (kv_observer, ("observe",)),
        ):
            if any(not callable(getattr(guard, name, None)) for name in names):
                raise LongContextSpoolError("invalid admission bundle dependency")
        self._cpu, self._memory, self._kv = cpu_guard, memory_guard, kv_observer
        self._nonce, self._max_active = nonce, max_active
        self._pid = os.getpid()
        self._lock = Lock()
        self._entries: dict[str, _Bundle] = {}
        self._closed = False
        self._revoked = 0

    def _pid_guard(self) -> None:
        if os.getpid() != self._pid:
            raise LongContextSpoolError("admission bundle inherited after fork")

    def _open(self) -> None:
        if self._closed:
            raise LongContextSpoolError("admission bundle closed")

    @staticmethod
    def _key(value: object, length: int) -> bool:
        return (type(value) is str and len(value) == length
                and all(ch in "0123456789abcdef" for ch in value))

    @staticmethod
    def _receipt(state: str, reason: str, *, bundle_id: str | None = None,
                 window_digest: str | None = None) -> dict[str, object]:
        return {
            "schema": _SCHEMA, "state": state, "reason": reason,
            "bundle_id": bundle_id, "window_digest": window_digest,
            "device": "cpu", "device_qualified": False,
            "cross_process_exclusive": False, "restart_state_durable": False,
            "is_admission_grant": False, "is_execution_lease": False,
            "is_memory_allocation": False,
            "requires_live_backend_revalidation": True,
        }

    def _kv_window(self, request: AdmissionBundleRequest) -> str | None:
        try:
            result = self._kv.observe(
                request.kv_layout, request.kv_window,
                expected_model_digest=request.expected_model_digest)
            if (type(result) is not dict
                    or result.get("schema") != "skeleton.ai.long-context-kv-compatibility.v1"
                    or result.get("state") != "compatible_observed"
                    or result.get("reason") != "backend_must_revalidate"
                    or any(result.get(name) is not False for name in (
                        "device_qualified", "is_admission_grant", "is_execution_lease",
                        "model_snapshot_attested", "tokenizer_state_attested",
                        "kv_tensor_contents_verified"))
                    or result.get("requires_live_backend_revalidation") is not True
                    or type(result.get("estimated_kv_bytes")) is not int
                    or not 1 <= result["estimated_kv_bytes"] <= request.memory.requested_bytes
                    or not self._key(result.get("window_digest"), 64)):
                return None
            return result["window_digest"]
        except Exception:
            return None

    def _cleanup(self, entry: _Bundle) -> None:
        # Independent guards can already be closed or revoked. Never let one
        # failed release prevent attempting the other, or resurrect a claim.
        for guard, key in ((self._cpu, entry.cpu_id),
                           (self._memory, entry.memory_id)):
            try:
                guard.release(key)
            except Exception:
                pass

    def _revoke(self, bundle_id: str) -> None:
        entry = self._entries.pop(bundle_id, None)
        if entry is not None:
            self._revoked += 1
            self._cleanup(entry)

    def reserve(self, request: AdmissionBundleRequest) -> dict[str, object]:
        if not isinstance(request, AdmissionBundleRequest):
            raise LongContextSpoolError("invalid admission bundle request")
        self._pid_guard()
        with self._lock:
            self._open()
            if len(self._entries) >= self._max_active:
                return self._receipt("hold", "bundle_capacity_exhausted")
            if any(item.request.cpu.stream_id == request.cpu.stream_id
                   for item in self._entries.values()):
                return self._receipt("hold", "duplicate_stream")
            digest = self._kv_window(request)
            if digest is None:
                return self._receipt("hold", "kv_identity_or_memory_unverified")
            memory_id = None
            cpu_id = None
            try:
                memory = self._memory.reserve(request.memory)
                # Capture a well-formed ID before checking the rest of the
                # receipt: a forged success flag must not leak a live claim.
                if type(memory) is dict and self._key(memory.get("reservation_id"), 48):
                    memory_id = memory["reservation_id"]
                if (type(memory) is not dict or memory.get("schema") !=
                    "skeleton.ai.long-context-memory-budget.v1"
                    or memory.get("state") != "reserved"
                    or memory.get("is_execution_lease") is not False
                    or memory.get("is_admission_grant") is not False
                    or memory.get("is_memory_allocation") is not False
                    or memory.get("device_qualified") is not False
                    or memory.get("requires_live_backend_revalidation") is not True):
                    return self._receipt("hold", "memory_reservation_unverified")
                if not self._key(memory_id, 48):
                    return self._receipt("hold", "memory_identity_unverified")
                cpu = self._cpu.reserve(request.cpu)
                if type(cpu) is dict and self._key(cpu.get("reservation_id"), 64):
                    cpu_id = cpu["reservation_id"]
                if (type(cpu) is not dict or cpu.get("state") != "reserved"
                    or cpu.get("schema") != "skeleton.ai.cpu-capacity-guard.v1"
                    or cpu.get("device") != "cpu"
                    or cpu.get("device_qualified") is not False
                    or cpu.get("is_execution_lease") is not False
                    or cpu.get("is_admission_grant") is not False
                    or cpu.get("cross_process_exclusive") is not False
                    or cpu.get("requires_live_backend_revalidation") is not True
                    or cpu.get("window_digest") != digest):
                    return self._receipt("hold", "cpu_reservation_unverified")
                if not self._key(cpu_id, 64):
                    return self._receipt("hold", "cpu_identity_unverified")
                bundle_id = self._nonce(32)
                if (not self._key(bundle_id, 64)
                        or bundle_id in self._entries):
                    return self._receipt("hold", "bundle_identity_unavailable")
                self._entries[bundle_id] = _Bundle(request, memory_id, cpu_id, digest)
                return self._receipt("reserved", "cooperative_only",
                                     bundle_id=bundle_id, window_digest=digest)
            except Exception:
                return self._receipt("hold", "bundle_dependency_unavailable")
            finally:
                # Publication transfers ownership of both IDs. Every other
                # exit rolls back independently, even after a partial success.
                if cpu_id is not None and not any(
                    entry.cpu_id == cpu_id for entry in self._entries.values()
                ):
                    try:
                        self._cpu.release(cpu_id)
                    except Exception:
                        pass
                if memory_id is not None and not any(
                    entry.memory_id == memory_id for entry in self._entries.values()
                ):
                    try:
                        self._memory.release(memory_id)
                    except Exception:
                        pass

    def reserve_fair_cycle(
        self, requests: tuple[AdmissionBundleRequest, ...], *,
        quantum_tokens: int = 256,
    ) -> dict[str, object]:
        """Atomic process-local reservation across KV, RAM, and CPU streams.

        The two underlying guards must support their own atomic fair-cycle
        operations. A failed/forged receipt never publishes a partial bundle;
        all recognizable reservation identities are released independently.
        Claims remain per-stream and require fresh backend revalidation.
        """
        if type(requests) is not tuple or not 1 <= len(requests) <= _MAX_ACTIVE:
            raise LongContextSpoolError("invalid admission fair cycle")
        if (type(quantum_tokens) is not int or not 1 <= quantum_tokens <= 4096
                or any(not isinstance(r, AdmissionBundleRequest) for r in requests)):
            raise LongContextSpoolError("invalid admission fair cycle request")
        names = [r.cpu.stream_id for r in requests]
        if len(set(names)) != len(names):
            raise LongContextSpoolError("duplicate admission fair cycle stream")
        self._pid_guard()
        with self._lock:
            self._open()
            ordered = tuple(sorted(requests, key=lambda r: r.cpu.stream_id))
            if (len(self._entries) + len(ordered) > self._max_active
                    or any(r.cpu.max_tokens > quantum_tokens for r in ordered)
                    or any(r.cpu.stream_id in (
                        entry.request.cpu.stream_id for entry in self._entries.values())
                        for r in ordered)):
                return {**self._receipt("hold", "fair_cycle_capacity_or_duplicate"),
                        "reservations": []}
            digests = [self._kv_window(r) for r in ordered]
            if any(digest is None for digest in digests):
                return {**self._receipt("hold", "fair_cycle_kv_unverified"),
                        "reservations": []}
            memory_keys: list[str] = []
            cpu_keys: list[str] = []
            published = False
            try:
                memory = self._memory.reserve_fair_cycle(
                    tuple(r.memory for r in ordered))
                if type(memory) is dict and type(memory.get("reservations")) is list:
                    memory_keys = [entry["reservation_id"] for entry in memory["reservations"]
                                   if type(entry) is dict
                                   and self._key(entry.get("reservation_id"), 48)]
                if (type(memory) is not dict
                        or memory.get("schema") != "skeleton.ai.long-context-memory-budget.v1"
                        or memory.get("state") != "reserved"
                        or memory.get("cycle_atomic_within_process") is not True
                        or memory.get("cross_process_exclusive") is not False
                        or any(memory.get(k) is not False for k in (
                            "is_execution_lease", "is_admission_grant",
                            "is_memory_allocation"))
                        or memory.get("requires_live_backend_revalidation") is not True
                        or type(memory.get("reservations")) is not list
                        or len(memory["reservations"]) != len(ordered)):
                    return {**self._receipt("hold", "fair_cycle_memory_unverified"),
                            "reservations": []}
                memory_map = {}
                from hashlib import sha256
                for entry in memory["reservations"]:
                    if type(entry) is not dict or not self._key(entry.get("reservation_id"), 48):
                        raise LongContextSpoolError("invalid fair-cycle RAM identity")
                    key = entry.get("stream_digest")
                    if (type(key) is not str or key in memory_map
                            or type(entry.get("requested_bytes")) is not int):
                        raise LongContextSpoolError("invalid fair-cycle RAM receipt")
                    memory_map[key] = entry
                for request in ordered:
                    digest = sha256(request.memory.stream_id.encode("ascii")).hexdigest()
                    if (digest not in memory_map
                            or memory_map[digest]["requested_bytes"] !=
                            request.memory.requested_bytes):
                        raise LongContextSpoolError("fair-cycle RAM stream mismatch")
                cpu = self._cpu.reserve_fair_cycle(
                    tuple(r.cpu for r in ordered), quantum_tokens=quantum_tokens)
                if type(cpu) is dict and type(cpu.get("reservations")) is list:
                    cpu_keys = [entry["reservation_id"] for entry in cpu["reservations"]
                                if type(entry) is dict
                                and self._key(entry.get("reservation_id"), 64)]
                if (type(cpu) is not dict
                        or cpu.get("schema") != "skeleton.ai.cpu-capacity-guard.v1"
                        or cpu.get("state") != "reserved"
                        or cpu.get("device") != "cpu"
                        or cpu.get("device_qualified") is not False
                        or cpu.get("is_execution_lease") is not False
                        or cpu.get("is_admission_grant") is not False
                        or cpu.get("cycle_atomic_within_process") is not True
                        or cpu.get("cross_process_exclusive") is not False
                        or cpu.get("requires_live_backend_revalidation") is not True
                        or type(cpu.get("reservations")) is not list
                        or len(cpu["reservations"]) != len(ordered)):
                    return {**self._receipt("hold", "fair_cycle_cpu_unverified"),
                            "reservations": []}
                cpu_map = {}
                from .long_context_progress import _name
                for entry in cpu["reservations"]:
                    if type(entry) is not dict or not self._key(entry.get("reservation_id"), 64):
                        raise LongContextSpoolError("invalid fair-cycle CPU identity")
                    key = entry.get("stream_digest")
                    if type(key) is not str or key in cpu_map:
                        raise LongContextSpoolError("duplicate fair-cycle CPU stream")
                    cpu_map[key] = entry
                for request, digest in zip(ordered, digests):
                    entry = cpu_map.get(_name(request.cpu.stream_id))
                    if (entry is None or entry.get("window_digest") != digest
                            or type(entry.get("max_tokens")) is not int
                            or entry["max_tokens"] != request.cpu.max_tokens):
                        raise LongContextSpoolError("fair-cycle CPU stream mismatch")
                bundle_keys = [self._nonce(32) for _ in ordered]
                if (any(not self._key(key, 64) or key in self._entries
                        for key in bundle_keys)
                        or len(set(bundle_keys)) != len(bundle_keys)):
                    raise LongContextSpoolError("fair-cycle bundle identity collision")
                receipts = []
                for request, digest, key in zip(ordered, digests, bundle_keys):
                    self._entries[key] = _Bundle(
                        request,
                        memory_map[sha256(request.memory.stream_id.encode("ascii")).hexdigest()]["reservation_id"],
                        cpu_map[_name(request.cpu.stream_id)]["reservation_id"],
                        digest)
                    receipts.append({
                        "stream_digest": _name(request.cpu.stream_id),
                        "bundle_id": key, "window_digest": digest,
                    })
                published = True
                return {**self._receipt("reserved", "cooperative_only"),
                        "reservations": receipts,
                        "cycle_atomic_within_process": True,
                        "cross_process_exclusive": False}
            except Exception:
                return {**self._receipt("hold", "fair_cycle_dependency_unavailable"),
                        "reservations": []}
            finally:
                if not published:
                    for guard, keys in ((self._cpu, cpu_keys),
                                        (self._memory, memory_keys)):
                        for key in set(keys):
                            try:
                                guard.release(key)
                            except Exception:
                                pass

    def claim(self, bundle_id: str, request: AdmissionBundleRequest) -> dict[str, object]:
        if not self._key(bundle_id, 64) or not isinstance(request, AdmissionBundleRequest):
            raise LongContextSpoolError("invalid admission bundle claim")
        self._pid_guard()
        with self._lock:
            self._open()
            entry = self._entries.get(bundle_id)
            if (entry is None or entry.state != "reserved"
                    or entry.request != request):
                return self._receipt("hold", "bundle_not_claimable")
            digest = self._kv_window(request)
            if digest is None or digest != entry.window_digest:
                self._revoke(bundle_id)
                return self._receipt("hold", "kv_changed_before_claim")
            try:
                cpu = self._cpu.claim(entry.cpu_id, request.cpu)
                if (type(cpu) is not dict or cpu.get("state") != "claimed"
                    or cpu.get("claimed") is not True
                    or cpu.get("schema") != "skeleton.ai.cpu-capacity-guard.v1"
                    or cpu.get("window_digest") != digest
                    or cpu.get("device_qualified") is not False
                    or cpu.get("is_execution_lease") is not False
                    or cpu.get("is_admission_grant") is not False
                    or cpu.get("cross_process_exclusive") is not False
                    or cpu.get("requires_live_backend_revalidation") is not True):
                    raise LongContextSpoolError("CPU claim unverified")
                memory = self._memory.claim(entry.memory_id, request.memory)
                if (type(memory) is not dict or memory.get("state") != "claimed"
                    or memory.get("schema") != "skeleton.ai.long-context-memory-budget.v1"
                    or memory.get("is_execution_lease") is not False
                    or memory.get("is_admission_grant") is not False
                    or memory.get("is_memory_allocation") is not False
                    or memory.get("device_qualified") is not False
                    or memory.get("requires_live_backend_revalidation") is not True):
                    raise LongContextSpoolError("memory claim unverified")
            except Exception:
                self._revoke(bundle_id)
                return self._receipt("hold", "claim_revalidation_failed")
            entry.state = "claimed"
            return self._receipt("claimed", "backend_must_revalidate",
                                 bundle_id=bundle_id, window_digest=digest)

    def release(self, bundle_id: str) -> bool:
        if not self._key(bundle_id, 64):
            raise LongContextSpoolError("invalid admission bundle identity")
        self._pid_guard()
        with self._lock:
            self._open()
            if bundle_id not in self._entries:
                return False
            self._revoke(bundle_id)
            return True

    def status(self) -> dict[str, object]:
        self._pid_guard()
        with self._lock:
            return {
                "schema": "skeleton.ai.long-context-admission-bundle-status.v1",
                "state": "closed" if self._closed else "diagnostic",
                "active": len(self._entries), "revocations": self._revoked,
                "device_qualified": False, "is_admission_grant": False,
                "is_execution_lease": False,
                "requires_live_backend_revalidation": True,
            }

    def close(self) -> None:
        self._pid_guard()
        with self._lock:
            if not self._closed:
                for key in tuple(self._entries):
                    self._revoke(key)
                self._closed = True


__all__ = ["AdmissionBundleRequest", "LongContextAdmissionBundle"]
