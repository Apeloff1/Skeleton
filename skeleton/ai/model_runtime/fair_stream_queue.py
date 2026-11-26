"""Deterministic fair token-stream admission for the canonical offline model runtime.

This is an admission and accounting control plane, not a second inference engine.
Execution remains with the canonical native/provider runtime. An issued lease
never proves GPU allocation, model execution, or physical memory reservation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import json
from threading import RLock
from typing import Mapping

from .iteration_scheduler import InferencePhase, IterationScheduler, IterationWork


SCHEMA = "skeleton.ai.fair-stream-checkpoint.v1"
PLAN_SCHEMA = "skeleton.ai.fair-stream-plan.v1"
MAX_REQUESTS = 4096
MAX_STREAMS = 64
MAX_TOKENS = 1 << 24
MAX_BYTES = (1 << 63) - 1
MAX_WAIT_ROUNDS = 4096


def _integer(name: str, value: object, *, minimum: int = 0, maximum: int = MAX_BYTES) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid " + name)
    return value


def _identifier(name: str, value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not value:
        raise ValueError("invalid " + name)
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("invalid " + name) from exc
    if len(raw) > maximum or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("invalid " + name)
    return value


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StreamRequest:
    request_id: str
    tenant_id: str
    phase: InferencePhase
    remaining_tokens: int
    bytes_per_token: int
    priority: int = 0

    def __post_init__(self) -> None:
        _identifier("request_id", self.request_id)
        _identifier("tenant_id", self.tenant_id, maximum=128)
        if not isinstance(self.phase, InferencePhase):
            raise ValueError("InferencePhase required")
        _integer("remaining_tokens", self.remaining_tokens, minimum=1, maximum=MAX_TOKENS)
        _integer("bytes_per_token", self.bytes_per_token, minimum=1)
        _integer("priority", self.priority, minimum=-100, maximum=100)


@dataclass(frozen=True, slots=True)
class MeasuredStreamBudget:
    """Caller-provided, explicit host measurements. Not a memory reservation.

    "operator" and "simulated" inputs must not be reported as OS observations.
    The caller must re-probe before dispatch, and execution must enforce its
    own actual backend allocation limits.
    """

    available_ram_bytes: int
    reserved_ram_bytes: int
    token_budget: int
    stream_slots: int
    pressure_ppm: int = 0
    thermal_hold: bool = False
    measurement: str = "operator"

    def __post_init__(self) -> None:
        _integer("available_ram_bytes", self.available_ram_bytes, maximum=MAX_BYTES)
        _integer("reserved_ram_bytes", self.reserved_ram_bytes, maximum=MAX_BYTES)
        _integer("token_budget", self.token_budget, maximum=MAX_TOKENS)
        _integer("stream_slots", self.stream_slots, maximum=MAX_STREAMS)
        _integer("pressure_ppm", self.pressure_ppm, maximum=1_000_000)
        if self.reserved_ram_bytes > self.available_ram_bytes:
            raise ValueError("reserved RAM exceeds available RAM")
        if type(self.thermal_hold) is not bool:
            raise ValueError("thermal_hold must be boolean")
        if self.measurement not in {"os_probe", "operator", "simulated"}:
            raise ValueError("unsupported measurement provenance")

    @property
    def effective_slots(self) -> int:
        if self.thermal_hold or self.pressure_ppm >= 950_000:
            return 0
        if self.pressure_ppm >= 800_000:
            return min(1, self.stream_slots)
        if self.pressure_ppm >= 600_000:
            return min(2, self.stream_slots)
        return self.stream_slots

    @property
    def effective_tokens(self) -> int:
        if self.effective_slots == 0:
            return 0
        # Integer-only conservative downscaling, with no minimum forced grant.
        return self.token_budget * (1_000_000 - self.pressure_ppm) // 1_000_000

    @property
    def available_for_streams(self) -> int:
        return self.available_ram_bytes - self.reserved_ram_bytes


@dataclass(frozen=True, slots=True)
class StreamLease:
    lease_id: str
    request_id: str
    tenant_id: str
    phase: InferencePhase
    tokens: int
    bytes_reserved: int
    round_number: int


@dataclass(frozen=True, slots=True)
class FairStreamPlan:
    leases: tuple[StreamLease, ...]
    deferred: tuple[str, ...]
    available_tokens: int
    available_ram_bytes: int
    checkpoint_digest: str
    digest: str


class FairStreamScheduler:
    """Bounded tenant-rotating planner with explicit execution acknowledgments.

    Each request is granted at most one slice per round. Tenant order rotates
    independently of priority. Within a tenant, bounded wait aging prevents
    persistent priority starvation. A pending lease fences all new planning:
    after a crash, restore cannot accidentally execute it twice.
    """

    def __init__(self, *, max_requests: int = MAX_REQUESTS, quantum: int = 128) -> None:
        self.max_requests = _integer("max_requests", max_requests, minimum=1, maximum=MAX_REQUESTS)
        self.quantum = _integer("quantum", quantum, minimum=1, maximum=8192)
        self._requests: dict[str, StreamRequest] = {}
        self._served: dict[str, int] = {}
        self._wait: dict[str, int] = {}
        self._pending: dict[str, StreamLease] = {}
        self._round = 0
        self._cursor = 0
        self._lock = RLock()

    @property
    def pending_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._pending))

    @property
    def request_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._requests))

    def submit(self, request: StreamRequest) -> None:
        if not isinstance(request, StreamRequest):
            raise ValueError("StreamRequest required")
        with self._lock:
            if request.request_id in self._requests:
                raise ValueError("duplicate stream request")
            if len(self._requests) >= self.max_requests:
                raise ValueError("stream queue full")
            self._requests[request.request_id] = request
            self._served[request.request_id] = 0
            self._wait[request.request_id] = 0

    def cancel(self, request_id: str) -> None:
        _identifier("request_id", request_id)
        with self._lock:
            if request_id not in self._requests:
                raise ValueError("unknown stream request")
            if any(lease.request_id == request_id for lease in self._pending.values()):
                raise ValueError("pending execution must be reconciled before cancellation")
            del self._requests[request_id]
            del self._served[request_id]
            del self._wait[request_id]

    def _best_for_tenant(self, tenant: str, selected: set[str]) -> StreamRequest | None:
        candidates = [
            item for item in self._requests.values()
            if item.tenant_id == tenant and item.request_id not in selected
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                -(item.priority + self._wait[item.request_id]),
                -self._wait[item.request_id],
                item.request_id,
            ),
        )

    def plan(self, budget: MeasuredStreamBudget) -> FairStreamPlan:
        if not isinstance(budget, MeasuredStreamBudget):
            raise ValueError("MeasuredStreamBudget required")
        with self._lock:
            if self._pending:
                raise ValueError("pending leases require execution reconciliation")
            token_left = budget.effective_tokens
            ram_left = budget.available_for_streams
            slots = budget.effective_slots
            tenants = sorted({item.tenant_id for item in self._requests.values()})
            leases: list[StreamLease] = []
            selected: set[str] = set()
            if tenants:
                offset = self._cursor % len(tenants)
                rotated = tenants[offset:] + tenants[:offset]
            else:
                rotated = []
            # A finite pass can grant at most one lease per request, even when
            # the same tenant has many requests. No request gets two leases.
            while slots > 0 and token_left > 0 and ram_left > 0:
                progress = False
                for tenant in rotated:
                    if slots <= 0 or token_left <= 0 or ram_left <= 0:
                        break
                    candidates = [
                        item for item in self._requests.values()
                        if item.tenant_id == tenant and item.request_id not in selected
                        and item.bytes_per_token <= ram_left
                    ]
                    if not candidates:
                        continue
                    request = min(
                        candidates,
                        key=lambda item: (
                            -(item.priority + self._wait[item.request_id]),
                            -self._wait[item.request_id],
                            item.request_id,
                        ),
                    )
                    canonical = IterationScheduler(
                        token_budget=min(token_left, self.quantum),
                        prefill_quantum=self.quantum,
                    ).plan((IterationWork(
                        request.request_id, request.phase, request.remaining_tokens,
                    ),))
                    tokens = min(canonical.slices[0].tokens, ram_left // request.bytes_per_token)
                    if tokens <= 0:
                        continue
                    reserved = tokens * request.bytes_per_token
                    lease_id = _digest({
                        "schema": "skeleton.ai.fair-stream-lease.v1",
                        "round": self._round,
                        "request_id": request.request_id,
                        "tenant_id": request.tenant_id,
                        "tokens": tokens,
                        "bytes": reserved,
                    })
                    lease = StreamLease(
                        lease_id, request.request_id, request.tenant_id,
                        request.phase, tokens, reserved, self._round,
                    )
                    leases.append(lease)
                    selected.add(request.request_id)
                    token_left -= tokens
                    ram_left -= reserved
                    slots -= 1
                    progress = True
                if not progress:
                    break
            self._pending = {lease.lease_id: lease for lease in leases}
            for request_id in self._requests:
                self._wait[request_id] = (
                    0 if request_id in selected
                    else min(MAX_WAIT_ROUNDS, self._wait[request_id] + 1)
                )
            self._round += 1
            if tenants:
                self._cursor = (self._cursor + 1) % len(tenants)
            deferred = tuple(sorted(set(self._requests) - selected))
            checkpoint_digest = str(self.checkpoint()["digest"])
            body = {
                "schema": PLAN_SCHEMA,
                "leases": [self._lease_dict(lease) for lease in leases],
                "deferred": list(deferred),
                "available_tokens": token_left,
                "available_ram_bytes": ram_left,
                "checkpoint_digest": checkpoint_digest,
            }
            return FairStreamPlan(
                tuple(leases), deferred, token_left, ram_left,
                checkpoint_digest, _digest(body),
            )

    def acknowledge(self, lease_id: str, *, consumed_tokens: int) -> None:
        _identifier("lease_id", lease_id, maximum=64)
        with self._lock:
            lease = self._pending.get(lease_id)
            if lease is None:
                raise ValueError("unknown or already reconciled lease")
            _integer("consumed_tokens", consumed_tokens, maximum=lease.tokens)
            request = self._requests.get(lease.request_id)
            if request is None or request.remaining_tokens < consumed_tokens:
                raise ValueError("stream state diverged from lease")
            remaining = request.remaining_tokens - consumed_tokens
            if remaining:
                self._requests[request.request_id] = StreamRequest(
                    request.request_id, request.tenant_id, request.phase,
                    remaining, request.bytes_per_token, request.priority,
                )
                self._served[request.request_id] += consumed_tokens
            else:
                del self._requests[request.request_id]
                del self._served[request.request_id]
                del self._wait[request.request_id]
            del self._pending[lease_id]

    @staticmethod
    def _lease_dict(lease: StreamLease) -> dict[str, object]:
        return {
            "lease_id": lease.lease_id,
            "request_id": lease.request_id,
            "tenant_id": lease.tenant_id,
            "phase": lease.phase.value,
            "tokens": lease.tokens,
            "bytes_reserved": lease.bytes_reserved,
            "round_number": lease.round_number,
        }

    def checkpoint(self) -> dict[str, object]:
        with self._lock:
            body: dict[str, object] = {
                "schema": SCHEMA,
                "max_requests": self.max_requests,
                "quantum": self.quantum,
                "round": self._round,
                "cursor": self._cursor,
                "requests": [
                    {
                        "request_id": item.request_id,
                        "tenant_id": item.tenant_id,
                        "phase": item.phase.value,
                        "remaining_tokens": item.remaining_tokens,
                        "bytes_per_token": item.bytes_per_token,
                        "priority": item.priority,
                        "served_tokens": self._served[item.request_id],
                        "wait_rounds": self._wait[item.request_id],
                    }
                    for _, item in sorted(self._requests.items())
                ],
                "pending": [
                    self._lease_dict(lease) for _, lease in sorted(self._pending.items())
                ],
            }
            return {**body, "digest": _digest(body)}

    @classmethod
    def restore(cls, checkpoint: Mapping[str, object]) -> "FairStreamScheduler":
        fields = {
            "schema", "max_requests", "quantum", "round", "cursor",
            "requests", "pending", "digest",
        }
        if not isinstance(checkpoint, Mapping) or set(checkpoint) != fields:
            raise ValueError("invalid stream checkpoint shape")
        if checkpoint["schema"] != SCHEMA:
            raise ValueError("unsupported stream checkpoint schema")
        digest = checkpoint["digest"]
        if type(digest) is not str or len(digest) != 64:
            raise ValueError("invalid stream checkpoint digest")
        body = {key: checkpoint[key] for key in fields if key != "digest"}
        try:
            expected = _digest(body)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid stream checkpoint encoding") from exc
        if not compare_digest(digest, expected):
            raise ValueError("stream checkpoint integrity mismatch")
        restored = cls(
            max_requests=_integer("max_requests", checkpoint["max_requests"], minimum=1, maximum=MAX_REQUESTS),
            quantum=_integer("quantum", checkpoint["quantum"], minimum=1, maximum=8192),
        )
        restored._round = _integer("round", checkpoint["round"])
        restored._cursor = _integer("cursor", checkpoint["cursor"], maximum=MAX_REQUESTS)
        raw_requests = checkpoint["requests"]
        raw_pending = checkpoint["pending"]
        if (type(raw_requests) is not list or len(raw_requests) > restored.max_requests
                or type(raw_pending) is not list or len(raw_pending) > MAX_STREAMS):
            raise ValueError("unbounded stream checkpoint")
        request_fields = {
            "request_id", "tenant_id", "phase", "remaining_tokens",
            "bytes_per_token", "priority", "served_tokens", "wait_rounds",
        }
        for item in raw_requests:
            if type(item) is not dict or set(item) != request_fields:
                raise ValueError("invalid checkpoint request")
            try:
                phase = InferencePhase(item["phase"])
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid checkpoint phase") from exc
            request = StreamRequest(
                item["request_id"], item["tenant_id"], phase,
                item["remaining_tokens"], item["bytes_per_token"], item["priority"],
            )
            restored.submit(request)
            restored._served[request.request_id] = _integer(
                "served_tokens", item["served_tokens"], maximum=MAX_TOKENS
            )
            restored._wait[request.request_id] = _integer(
                "wait_rounds", item["wait_rounds"], maximum=MAX_WAIT_ROUNDS
            )
        lease_fields = {
            "lease_id", "request_id", "tenant_id", "phase", "tokens",
            "bytes_reserved", "round_number",
        }
        pending_requests: set[str] = set()
        for item in raw_pending:
            if type(item) is not dict or set(item) != lease_fields:
                raise ValueError("invalid checkpoint lease")
            request_id = _identifier("request_id", item["request_id"])
            request = restored._requests.get(request_id)
            if request is None or request_id in pending_requests:
                raise ValueError("checkpoint pending request mismatch")
            try:
                phase = InferencePhase(item["phase"])
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid checkpoint lease phase") from exc
            tokens = _integer("tokens", item["tokens"], minimum=1, maximum=request.remaining_tokens)
            reserved = _integer("bytes_reserved", item["bytes_reserved"], minimum=1)
            round_number = _integer("round_number", item["round_number"])
            if (round_number >= restored._round or phase != request.phase
                    or item["tenant_id"] != request.tenant_id
                    or reserved != tokens * request.bytes_per_token):
                raise ValueError("checkpoint lease does not bind request")
            lease_id = _identifier("lease_id", item["lease_id"], maximum=64)
            if lease_id != _digest({
                "schema": "skeleton.ai.fair-stream-lease.v1",
                "round": round_number, "request_id": request_id,
                "tenant_id": request.tenant_id, "tokens": tokens, "bytes": reserved,
            }):
                raise ValueError("checkpoint lease identity mismatch")
            if lease_id in restored._pending:
                raise ValueError("duplicate checkpoint lease")
            restored._pending[lease_id] = StreamLease(
                lease_id, request_id, request.tenant_id, phase,
                tokens, reserved, round_number,
            )
            pending_requests.add(request_id)
        return restored


__all__ = [
    "FairStreamPlan", "FairStreamScheduler", "MeasuredStreamBudget",
    "StreamLease", "StreamRequest",
]
