"""Source-bound offline stream dispatch: fresh pressure gate and durable receipts.

This adapter is deliberately CPU-only. The sampler authorizes a *planning*
quantum, not physical memory; the trusted execution owner must enforce actual
backend quotas, cancellation and durable result publication. A callback that
may have executed is never automatically retried after an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import TYPE_CHECKING, Callable, Mapping, Protocol

if TYPE_CHECKING:
    from .fair_stream_execution_journal import FairStreamExecutionJournal
    from .fair_stream_recovery import RecoveryAuthorization

from .fair_stream_live_budget import LiveStreamBudgetSampler
from .fair_stream_revalidation import bound_revalidation_budget
from .fair_stream_queue import MeasuredStreamBudget, StreamRequest, MAX_TOKENS
from .fair_stream_session import (
    DispatchPermit, DurableFairStreamSession,
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
        *, storage_path: str, whole_request: bool = False,
        queued_authority: Callable[[dict[str, object]], None] | None = None,
        cancel_cleanup: Callable[[str], None] | None = None,
    ) -> None:
        if type(whole_request) is not bool:
            raise ValueError("explicit whole-request policy required")
        if not isinstance(session, DurableFairStreamSession):
            raise ValueError("durable authenticated session required")
        if session.whole_request != whole_request:
            raise ValueError("dispatch policy differs from authenticated session")
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
        self._whole_request = whole_request
        if ((queued_authority is not None and not callable(queued_authority))
                or (cancel_cleanup is not None and not callable(cancel_cleanup))):
            raise ValueError("trusted queue lifecycle callbacks required")
        self._queued_authority = queued_authority
        self._cancel_cleanup = cancel_cleanup
        self._lock = RLock()
        self._issued: dict[str, DispatchPermit] = {}
        self._issued_token_budget: int | None = None
        self._uncertain = False
        self._executing = False

    @property
    def uncertain(self) -> bool:
        with self._lock:
            return self._uncertain

    def status_snapshot(self) -> tuple[int, int, bool, bool]:
        """One verified generation; restarted pending work is uncertain.

        A known in-process deferred permit is distinct from a persisted
        lease whose execution outcome cannot be established by this owner.
        """
        with self._lock:
            state = self._session.verify()
            pending = state["checkpoint"]["pending"]
            if type(pending) is not list:
                raise DispatchUncertain("invalid pending checkpoint")
            known = (len(pending) == len(self._issued) == 1
                     and type(pending[0]) is dict
                     and pending[0].get("lease_id") in self._issued)
            return (state["generation"], len(pending), self._session.quarantined,
                    self._uncertain or self._executing or bool(pending and not known))

    def _require_no_pending(self) -> None:
        if self._executing or self._issued or self._uncertain or self._session.pending_ids():
            raise DispatchUncertain("pending dispatch must be reconciled")

    def submit(self, request: StreamRequest) -> dict[str, object]:
        with self._lock:
            self._require_no_pending()
            return self._session.submit(request)

    def cancel(self, request_id: str, *, tenant_id: str | None = None) -> dict[str, object]:
        with self._lock:
            self._require_no_pending()
            # Authenticated native callers must supply tenant identity from
            # their principal, never from an untrusted payload. Check before
            # attempting a durable transition, to avoid quarantining on denial.
            if self._cancel_cleanup is not None and tenant_id is None:
                raise ValueError("authenticated tenant required for native cancellation")
            if tenant_id is not None and (type(tenant_id) is not str or not tenant_id):
                raise ValueError("authenticated tenant required")
            state = self._session.verify()
            if tenant_id is not None:
                requests = state["checkpoint"]["requests"]
                matches = [r for r in requests if r["request_id"] == request_id
                           and r["tenant_id"] == tenant_id]
                if len(matches) != 1:
                    raise ValueError("tenant does not own queued request")
            changed = self._session.cancel(
                request_id, tenant_id=tenant_id,
                expected_anchor=(state["generation"], state["digest"]),
            )
            if self._cancel_cleanup is not None:
                self._cancel_cleanup(request_id)
            return changed

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
            type(budget) is not MeasuredStreamBudget
            or budget.token_budget > token_budget
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
            if self._executing or self._uncertain or self._issued or self._session.pending_ids():
                raise DispatchUncertain("pending execution requires durable reconciliation")
            budget, observation = self._sample(token_budget)
            if observation.effective_slots == 0 or observation.effective_tokens == 0:
                raise DispatchDeferred("resource pressure prohibits dispatch")
            anchor = None
            if self._queued_authority is not None:
                snapshot = self._session.verify()
                try:
                    self._queued_authority(snapshot)
                except (ValueError, RuntimeError, OSError) as exc:
                    raise DispatchDeferred("queued authorization unavailable; explicit cancellation required") from exc
                anchor = (snapshot["generation"], snapshot["digest"])
            permits, _ = self._session.plan(
                budget, whole_request=self._whole_request, expected_anchor=anchor,
            )
            if len(permits) > 1:
                self._uncertain = True
                raise DispatchUncertain("non-atomic multi-lease plan forbidden")
            self._issued = {permit.lease_id: permit for permit in permits}
            # Persist no new authority. Retain the pre-discount ceiling only
            # while this process owns the issued permit.
            self._issued_token_budget = token_budget if permits else None
            return permits, observation

    def dispatch_next(self, *, token_budget: int) -> tuple[DispatchPermit | None, dict[str, object] | None, DispatchObservation]:
        """Plan once or explicitly resume a known, not-yet-started permit.

        Fresh observation is returned from the actual execution preflight,
        not the potentially stale initial plan. No permit is reconstructed
        from persistent pending state. The lock covers planning and dispatch
        together, including receipt acknowledgement.
        """
        if type(token_budget) is not int or not 1 <= token_budget <= MAX_TOKENS:
            raise ValueError("bounded positive token budget required")
        with self._lock:
            if self._uncertain or self._executing:
                raise DispatchUncertain("execution outcome requires reconciliation")
            if self._issued:
                if len(self._issued) != 1:
                    self._uncertain = True
                    raise DispatchUncertain("non-atomic multi-lease plan forbidden")
                if token_budget != self._issued_token_budget:
                    raise DispatchDeferred("resume requires the original planning token budget")
                permit = next(iter(self._issued.values()))
            else:
                permits, observation = self.plan_live(token_budget=token_budget)
                if not permits:
                    return None, None, observation
                permit = permits[0]
            state, observation = self._execute_once_observed(permit)
            return permit, state, observation

    def _validate_pending(self, permit: DispatchPermit) -> dict[str, object]:
        # Dataclass equality is insufficient: bool == 1, and an attacker who
        # supplies a forged permit can otherwise alias a one-token lease.
        # Reject malformed identity before any fresh sampling or backend call.
        if (type(permit) is not DispatchPermit
                or type(permit.lease_id) is not str
                or type(permit.request_id) is not str
                or type(permit.generation) is not int
                or type(permit.checkpoint_digest) is not str
                or type(permit.tokens) is not int
                or type(permit.bytes_reserved) is not int
                or type(permit.device_qualified) is not bool):
            raise DispatchUncertain("canonical typed dispatch permit required")
        state = self._session.verify()
        if (
            self._issued.get(permit.lease_id) != permit
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

    def reconcile_committed(
        self, *, journal: "FairStreamExecutionJournal",
        authorization: "RecoveryAuthorization", recovery_key: bytes,
    ) -> dict[str, object]:
        """Explicitly retire an ALREADY committed lease; never run a backend.

        This administrative in-process seam must only be exposed behind the
        application's independent operator authentication. It cannot repair
        an uncommitted execution, an unknown result or a rolled-back anchor.
        """
        from .fair_stream_execution_journal import (
            ExecutionOutcomeUnknown, FairStreamExecutionJournal,
        )
        from .fair_stream_recovery import (
            RecoveryAuthorization, verify_recovery_authorization,
        )

        if type(journal) is not FairStreamExecutionJournal:
            raise ValueError("canonical committed execution journal required")
        with self._lock:
            if self._executing:
                raise DispatchUncertain("execution owner is still active")
            state = self._session.verify()
            checkpoint = state.get("checkpoint")
            pending = checkpoint.get("pending") if isinstance(checkpoint, Mapping) else None
            if type(pending) is not list or len(pending) != 1:
                raise DispatchUncertain("exactly one pending lease required")
            lease = pending[0]
            if type(lease) is not dict:
                raise DispatchUncertain("invalid pending lease")
            try:
                permit = DispatchPermit(
                    lease_id=lease["lease_id"],
                    request_id=lease["request_id"],
                    generation=state["generation"],
                    checkpoint_digest=state["checkpoint_digest"],
                    tokens=lease["tokens"],
                    bytes_reserved=lease["bytes_reserved"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise DispatchUncertain("invalid canonical pending lease") from exc
            if self._issued and self._issued.get(permit.lease_id) != permit:
                raise DispatchUncertain("in-memory lease differs from durable custody")
            verify_recovery_authorization(
                authorization, recovery_key=recovery_key,
                state=state, lease_id=permit.lease_id,
            )
            # Never call execute_and_commit, even if the journal has only a
            # RUNNING intent. The execution result must already be durable.
            try:
                receipt = journal.recover_committed_receipt(permit)
                updated = self._session.acknowledge(receipt, whole_request=self._whole_request)
            except BaseException as exc:
                # SQLite I/O errors, interruption and malformed receipts are
                # also uncertain outcomes. Do not leave the app reporting an
                # apparently healthy executor after a failed reconciliation.
                self._uncertain = True
                raise DispatchUncertain(
                    "committed receipt unavailable or custody reconciliation failed"
                ) from exc
            self._issued.clear()
            self._issued_token_budget = None
            self._uncertain = False
            return updated

    def execute_once(self, permit: DispatchPermit) -> dict[str, object]:
        """Execute at most once, with a fresh OS re-probe and signed receipt.

        If the backend raises, a result may already have been committed. The
        permit remains pending and this adapter refuses automatic retry.
        """
        state, _ = self._execute_once_observed(permit)
        return state

    def _execute_once_observed(self, permit: DispatchPermit) -> tuple[dict[str, object], DispatchObservation]:
        with self._lock:
            if self._uncertain or self._executing:
                raise DispatchUncertain("execution outcome requires reconciliation")
            state = self._validate_pending(permit)
            ceiling = self._issued_token_budget
            if type(ceiling) is not int or not permit.tokens <= ceiling <= MAX_TOKENS:
                self._uncertain = True
                raise DispatchUncertain("original planning budget unavailable; reconcile")
            # Do not discount the already-discounted lease a second time.
            _, observation = self._sample(ceiling)
            if (
                observation.effective_slots < 1
                or observation.effective_tokens < permit.tokens
                or observation.ram_headroom_bytes < permit.bytes_reserved
            ):
                raise DispatchDeferred("fresh pressure probe denies pending lease")
            # A live OS probe can block or yield while another process moves
            # the independent CAS anchor. Re-read both durable authorities
            # immediately before invoking the side-effecting native backend.
            # The journal's one-use execution claim remains the final
            # cross-process fence; this check narrows the sampling TOCTOU gap.
            try:
                refreshed = self._validate_pending(permit)
                if (refreshed["generation"] != state["generation"]
                        or refreshed["checkpoint_digest"] != state["checkpoint_digest"]):
                    raise DispatchUncertain("durable lease changed during resource probe")
            except BaseException as exc:
                self._uncertain = True
                raise DispatchUncertain(
                    "durable lease changed during resource probe; reconciliation required"
                ) from exc
            self._executing = True
            try:
                try:
                    with bound_revalidation_budget(permit, ceiling):
                        receipt = self._owner.execute_and_commit(permit, refreshed)
                except BaseException as exc:
                    self._uncertain = True
                    raise DispatchUncertain(
                        "backend outcome uncertain; do not re-execute pending lease"
                    ) from exc
                # Never accept an unsigned result or manufacture a completion.
                try:
                    updated = self._session.acknowledge(receipt, whole_request=self._whole_request)
                except BaseException as exc:
                    self._uncertain = True
                    raise DispatchUncertain(
                        "execution receipt not durably reconciled"
                    ) from exc
                del self._issued[permit.lease_id]
                self._issued_token_budget = None
                return updated, observation
            finally:
                self._executing = False
