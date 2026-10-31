"""Source-bound offline stream dispatch: fresh pressure gate and durable receipts.

This adapter is deliberately CPU-only. The sampler authorizes a *planning*
quantum, not physical memory; the trusted execution owner must enforce actual
backend quotas, cancellation and durable result publication. A callback that
may have executed is never automatically retried after an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Mapping, Protocol

from .fair_stream_live_budget import LiveStreamBudgetSampler
from .fair_stream_queue import MeasuredStreamBudget, StreamRequest, MAX_TOKENS
from .fair_stream_session import (
    CustodyQuarantined, DispatchPermit, DurableFairStreamSession,
)


class DispatchDeferred(RuntimeError):
    """No execution began; a new live observation is required."""


class DispatchUncertain(RuntimeError):
    """Execution may have occurred; reconcile durable owner result first."""


class DurableExecutionOwner(Protocol):
    """Trusted backend: commit actual result before returning signed receipt.

    This protocol does not implement a model or grant authorization to an
    arbitrary caller. The session verifies the receipt with its independent
    execution key. A backend must independently enforce resource quotas.
    """

    def execute_and_commit(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class DispatchObservation:
    """Measured admission metadata, never hardware/device qualification."""

    pressure_ppm: int
    effective_tokens: int
    effective_slots: int
    ram_headroom_bytes: int
    auxiliary_telemetry_incomplete: bool
    gpu_device_qualified: bool = False


class GuardedFairStreamDispatch:
    """Single-flight, fail-closed bridge to the canonical durable session.

    A round intentionally admits at most ONE lease. Canonical multi-tenant
    fairness rotates across rounds; multi-lease execution awaits an atomic
    batch-receipt contract, since each single receipt advances generation.
    No restart reconstructs an execution permit from a pending checkpoint.
    """

    def __init__(
        self, session: DurableFairStreamSession,
        sampler: LiveStreamBudgetSampler,
        owner: DurableExecutionOwner,
        *, storage_path: str,
    ) -> None:
        if not isinstance(session, DurableFairStreamSession):
            raise ValueError("durable authenticated session required")
        # Only the canonical sampler can supply the dispatch observation.
        # The application must treat this Python process as trusted code.
        if type(sampler) is not LiveStreamBudgetSampler:
            raise ValueError("canonical live OS sampler required")
        if not callable(getattr(owner, "execute_and_commit", None)):
            raise ValueError("trusted durable execution owner required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected storage volume required")
        self._session = session
        self._sampler = sampler
        self._owner = owner
        self._storage_path = storage_path
        self._lock = RLock()
        self._issued: dict[str, DispatchPermit] = {}
        self._uncertain = False

    @property
    def uncertain(self) -> bool:
        return self._uncertain

    def submit(self, request: StreamRequest) -> dict[str, object]:
        with self._lock:
            if self._issued or self._uncertain:
                raise DispatchUncertain("pending dispatch must be reconciled")
            return self._session.submit(request)

    def cancel(self, request_id: str) -> dict[str, object]:
        with self._lock:
            if self._issued or self._uncertain:
                raise DispatchUncertain("pending dispatch must be reconciled")
            return self._session.cancel(request_id)

    def _sample(self, token_budget: int) -> tuple[MeasuredStreamBudget, DispatchObservation]:
        if type(token_budget) is not int or not 1 <= token_budget <= MAX_TOKENS:
            raise ValueError("bounded positive token budget required")
        try:
            budget, evidence = self._sampler.sample(
                token_budget=token_budget, storage_path=self._storage_path,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise DispatchDeferred("live resource measurement unavailable") from exc
        if (
            not isinstance(budget, MeasuredStreamBudget)
            or budget.measurement != "os_probe"
            or type(evidence) is not dict
            or evidence.get("measurement") != "os_probe"
            or evidence.get("gpu_device_qualified") is not False
            or evidence.get("physical_memory_reserved") is not False
            or type(evidence.get("auxiliary_telemetry_incomplete")) is not bool
        ):
            raise DispatchDeferred("untrusted or incomplete OS provenance")
        # One receipt advances the generation. Never issue more than one
        # permit until an atomic multi-lease receipt protocol is available.
        single = replace(budget, stream_slots=min(1, budget.stream_slots))
        observation = DispatchObservation(
            pressure_ppm=single.pressure_ppm,
            effective_tokens=single.effective_tokens,
            effective_slots=single.effective_slots,
            ram_headroom_bytes=single.available_for_streams,
            auxiliary_telemetry_incomplete=evidence["auxiliary_telemetry_incomplete"],
        )
        return single, observation

    def plan_live(
        self, *, token_budget: int,
    ) -> tuple[tuple[DispatchPermit, ...], DispatchObservation]:
        with self._lock:
            if self._uncertain or self._issued or self._session.pending_ids():
                raise DispatchUncertain("pending execution requires durable reconciliation")
            budget, observation = self._sample(token_budget)
            if observation.effective_slots == 0 or observation.effective_tokens == 0:
                raise DispatchDeferred("resource pressure prohibits dispatch")
            permits, _ = self._session.plan(budget)
            if len(permits) > 1:
                self._uncertain = True
                raise DispatchUncertain("non-atomic multi-lease plan forbidden")
            self._issued = {permit.lease_id: permit for permit in permits}
            return permits, observation

    def _validate_pending(self, permit: DispatchPermit) -> dict[str, object]:
        state = self._session.verify()
        if (
            self._issued.get(permit.lease_id) != permit
            or type(permit) is not DispatchPermit
            or permit.device_qualified
            or permit.generation != state["generation"]
            or permit.checkpoint_digest != state["checkpoint_digest"]
        ):
            raise DispatchUncertain("stale or unissued dispatch permit")
        checkpoint = state["checkpoint"]
        pending = checkpoint["pending"]
        if type(pending) is not list or len(pending) != 1:
            raise DispatchUncertain("unexpected pending lease cardinality")
        lease = pending[0]
        if (
            type(lease) is not dict
            or lease.get("lease_id") != permit.lease_id
            or lease.get("request_id") != permit.request_id
            or lease.get("tokens") != permit.tokens
            or lease.get("bytes_reserved") != permit.bytes_reserved
        ):
            raise DispatchUncertain("durable lease differs from permit")
        return state

    def execute_once(self, permit: DispatchPermit) -> dict[str, object]:
        """Execute at most once, with a fresh OS re-probe and signed receipt.

        If the backend raises, a result may already have been committed. The
        permit remains pending and this adapter refuses automatic retry.
        """
        with self._lock:
            if self._uncertain:
                raise DispatchUncertain("execution outcome requires reconciliation")
            state = self._validate_pending(permit)
            budget, observation = self._sample(permit.tokens)
            if (
                observation.effective_slots < 1
                or observation.effective_tokens < permit.tokens
                or observation.ram_headroom_bytes < permit.bytes_reserved
            ):
                raise DispatchDeferred("fresh pressure probe denies pending lease")
            try:
                receipt = self._owner.execute_and_commit(permit, state)
            except BaseException as exc:
                self._uncertain = True
                raise DispatchUncertain(
                    "backend outcome uncertain; do not re-execute pending lease"
                ) from exc
            # Never accept an unsigned result or manufacture a completion.
            try:
                updated = self._session.acknowledge(receipt)
            except BaseException as exc:
                self._uncertain = True
                raise DispatchUncertain(
                    "execution receipt not durably reconciled"
                ) from exc
            del self._issued[permit.lease_id]
            return updated
