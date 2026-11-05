"""Fail-closed dispatch boundary for authenticated offline fair-stream sessions.

No model may be dispatched solely from an unpersisted in-memory plan.
The caller supplies an independently durable high-watermark, trusted local
SQLite connection, real OS probes, and an execution owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Mapping, Protocol

from .fair_stream_queue import MeasuredStreamBudget, StreamRequest
from .fair_stream_sqlite import DurableFairStreamStore


class CustodyQuarantined(RuntimeError):
    """A transaction or independent high-watermark cannot be reconciled."""


class TrustedHighWatermark(Protocol):
    """App-owned independent durable CAS store, NOT the SQLite custody row."""

    def initialize(self, *, generation: int, digest: str) -> None: ...

    def read(self) -> tuple[int, str]: ...

    def advance(
        self, *, expected_generation: int, expected_digest: str,
        generation: int, digest: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    """Durable planner intent, not a GPU reservation or execution receipt."""

    lease_id: str
    request_id: str
    generation: int
    checkpoint_digest: str
    tokens: int
    bytes_reserved: int
    device_qualified: bool = False


class DurableFairStreamSession:
    """Only exposes leases after SQLite COMMIT and external CAS both succeed.

    A crash after SQLite COMMIT but before independent CAS deliberately makes
    the session unrecoverable without an explicit trusted reconciliation.
    The adapter must not guess which side is authoritative or reissue a lease.
    """

    def __init__(
        self, store: DurableFairStreamStore,
        watermark: TrustedHighWatermark,
    ) -> None:
        if not isinstance(store, DurableFairStreamStore):
            raise ValueError("canonical durable fair-stream store required")
        if not all(callable(getattr(watermark, name, None)) for name in (
            "initialize", "read", "advance",
        )):
            raise ValueError("trusted high-watermark CAS required")
        self._store = store
        self._watermark = watermark
        self._lock = RLock()
        self._quarantined = False
        self.verify()

    @classmethod
    def bootstrap(
        cls, store: DurableFairStreamStore,
        watermark: TrustedHighWatermark,
    ) -> "DurableFairStreamSession":
        """One-time initialization; a failed external CAS is never retried."""
        envelope = store.initialize()
        watermark.initialize(
            generation=envelope["generation"], digest=envelope["digest"],
        )
        return cls(store, watermark)

    @property
    def quarantined(self) -> bool:
        return self._quarantined

    def _trusted(self) -> tuple[int, str]:
        if self._quarantined:
            raise CustodyQuarantined("session quarantined; explicit recovery required")
        try:
            generation, digest = self._watermark.read()
            if type(generation) is not int or not 0 <= generation < (1 << 63):
                raise ValueError("invalid trusted generation")
            if type(digest) is not str or len(digest) != 64 or any(
                c not in "0123456789abcdef" for c in digest
            ):
                raise ValueError("invalid trusted digest")
            return generation, digest
        except Exception as exc:
            self._quarantined = True
            raise CustodyQuarantined("trusted high-watermark unavailable") from exc

    def verify(self) -> dict[str, object]:
        with self._lock:
            generation, digest = self._trusted()
            try:
                owner = self._store.load(
                    expected_generation=generation, expected_digest=digest,
                )
                return owner.export()
            except Exception as exc:
                self._quarantined = True
                raise CustodyQuarantined(
                    "durable state diverges from trusted high-watermark"
                ) from exc

    def _transition(
        self, *, action: str, **kwargs: object,
    ) -> tuple[object | None, dict[str, object]]:
        with self._lock:
            generation, digest = self._trusted()
            try:
                plan, envelope = self._store.transition(
                    expected_generation=generation, expected_digest=digest,
                    action=action, **kwargs,
                )
                # No dispatch is authorized before this independent CAS.
                self._watermark.advance(
                    expected_generation=generation, expected_digest=digest,
                    generation=envelope["generation"], digest=envelope["digest"],
                )
                return plan, envelope
            except Exception as exc:
                # Even when the SQLite update succeeded and the anchor failed,
                # no further work can be admitted or dispatched from this
                # process. A new process also detects the mismatch on verify.
                self._quarantined = True
                raise CustodyQuarantined(
                    "fair-stream transaction requires trusted reconciliation"
                ) from exc

    def submit(self, request: StreamRequest) -> dict[str, object]:
        if not isinstance(request, StreamRequest):
            raise ValueError("canonical stream request required")
        _, state = self._transition(action="submit", request=request)
        return state

    def cancel(self, request_id: str) -> dict[str, object]:
        _, state = self._transition(action="cancel", request_id=request_id)
        return state

    def plan(
        self, budget: MeasuredStreamBudget,
    ) -> tuple[tuple[DispatchPermit, ...], dict[str, object]]:
        """Require a fresh trusted OS probe; never dispatch simulated inputs."""
        if not isinstance(budget, MeasuredStreamBudget):
            raise ValueError("canonical measured stream budget required")
        if budget.measurement != "os_probe":
            raise ValueError("trusted live OS measurement required for dispatch")
        plan, state = self._transition(action="plan", budget=budget)
        if plan is None:
            raise CustodyQuarantined("canonical planner produced no plan")
        permits = tuple(
            DispatchPermit(
                lease_id=lease.lease_id, request_id=lease.request_id,
                generation=state["generation"],
                checkpoint_digest=state["checkpoint_digest"],
                tokens=lease.tokens, bytes_reserved=lease.bytes_reserved,
            )
            for lease in plan.leases
        )
        return permits, state

    def acknowledge(self, receipt: Mapping[str, object]) -> dict[str, object]:
        """Only canonical execution-owner MAC receipts can retire leases."""
        if not isinstance(receipt, Mapping):
            raise ValueError("signed execution receipt required")
        _, state = self._transition(action="acknowledge", receipt=receipt)
        return state

    def pending_ids(self) -> tuple[str, ...]:
        with self._lock:
            generation, digest = self._trusted()
            try:
                owner = self._store.load(
                    expected_generation=generation, expected_digest=digest,
                )
                return owner.pending_ids
            except Exception as exc:
                self._quarantined = True
                raise CustodyQuarantined("pending lease state unverifiable") from exc
