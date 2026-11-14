"""Source-bound offline stream dispatch: fresh pressure gate and durable receipts.

This adapter is deliberately CPU-only. The sampler authorizes a *planning*
quantum, not physical memory; the trusted execution owner must enforce actual
backend quotas, cancellation and durable result publication. A callback that
may have executed is never automatically retried after an exception.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from threading import RLock
from typing import Callable, Mapping, Protocol

from .fair_stream_live_budget import LiveStreamBudgetSampler
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
        *, storage_path: str,
        revoke_queued_prompt: Callable[[str], None] | None = None,
        validate_queued_prompts: Callable[[list[dict[str, object]]], None] | None = None,
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
        if revoke_queued_prompt is not None and not callable(revoke_queued_prompt):
            raise ValueError('queued prompt revoke hook must be callable')
        self._revoke_queued_prompt = revoke_queued_prompt
        if validate_queued_prompts is not None and not callable(validate_queued_prompts):
            raise ValueError("queued prompt validation hook must be callable")
        self._validate_queued_prompts = validate_queued_prompts
        self._lock = RLock()
        self._issued: dict[str, DispatchPermit] = {}
        self._issued_budget: int | None = None
        self._issued_observation: DispatchObservation | None = None
        self._whole_request = getattr(owner, "whole_request", False) is True
        self._uncertain = False
        self._attempting = False
        self._last_execution_observation: DispatchObservation | None = None

    def _require_owner_process(self) -> None:
        self._session._require_owner_process()

    @contextmanager
    def _execution_attempt(self):
        self._require_owner_process()
        with self._lock:
            if self._attempting:
                raise DispatchDeferred("reentrant execution is forbidden")
            self._attempting = True
            self._last_execution_observation = None
            try:
                yield
            finally:
                self._attempting = False

    @property
    def uncertain(self) -> bool:
        return self._uncertain

    def submit(self, request: StreamRequest) -> dict[str, object]:
        self._require_owner_process()
        with self._lock:
            if self._issued or self._uncertain or self._session.pending_ids():
                raise DispatchUncertain("pending dispatch must be reconciled")
            return self._session.submit(request)

    def cancel(self, request_id: str, *, tenant_id: str | None = None) -> dict[str, object]:
        """Cancel queued work only; never wait behind running model I/O."""
        if type(request_id) is not str or not request_id or len(request_id) > 256:
            raise ValueError("invalid queued request identity")
        if tenant_id is not None and (type(tenant_id) is not str or not tenant_id):
            raise ValueError("invalid authenticated tenant")
        self._require_owner_process()
        if not self._lock.acquire(blocking=False):
            raise DispatchDeferred("active dispatch prevents queued cancellation")
        try:
            if self._issued or self._uncertain or self._session.pending_ids():
                raise DispatchUncertain("pending dispatch must be reconciled")
            state = self._session.verify()
            matching = [row for row in state["checkpoint"]["requests"]
                        if row["request_id"] == request_id]
            if len(matching) != 1 or (
                tenant_id is not None and matching[0]["tenant_id"] != tenant_id
            ):
                raise ValueError("unknown authorized queued request")
            # Deny execution authority before removing durable queued state.
            # A failed revoke leaves the request available for explicit cancel
            # retry; no permanent uncertain-execution state is fabricated.
            if self._revoke_queued_prompt is not None:
                try:
                    self._revoke_queued_prompt(request_id)
                except Exception as exc:
                    raise DispatchDeferred("queued prompt revocation unavailable") from exc
            return self._session.cancel(request_id)
        finally:
            self._lock.release()

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
        self._require_owner_process()
        with self._lock:
            if self._attempting:
                raise DispatchDeferred("reentrant planning is forbidden")
            if self._uncertain or self._issued or self._session.pending_ids():
                raise DispatchUncertain("pending execution requires durable reconciliation")
            budget, observation = self._sample(token_budget)
            if observation.effective_slots == 0 or observation.effective_tokens == 0:
                raise DispatchDeferred("resource pressure prohibits dispatch")
            if self._validate_queued_prompts is not None:
                state = self._session.verify()
                try:
                    self._validate_queued_prompts(state["checkpoint"]["requests"])
                except (RuntimeError, ValueError) as exc:
                    raise DispatchDeferred("queued prompt authorization unavailable") from exc
            permits, _ = self._session.plan(budget, whole_request=self._whole_request)
            if len(permits) > 1:
                self._uncertain = True
                raise DispatchUncertain("non-atomic multi-lease plan forbidden")
            self._issued = {permit.lease_id: permit for permit in permits}
            self._issued_budget = token_budget if permits else None
            self._issued_observation = observation if permits else None
            return permits, observation

    def resume_or_plan_live(self, *, token_budget: int) -> tuple[tuple[DispatchPermit, ...], DispatchObservation]:
        """Resume only an in-process permit whose backend has not been invoked.

        A deferred pressure probe leaves the permit outstanding. A restart,
        backend exception or failed receipt acknowledgement never grants replay.
        """
        if type(token_budget) is not int or not 1 <= token_budget <= MAX_TOKENS:
            raise ValueError("bounded positive token budget required")
        self._require_owner_process()
        with self._lock:
            if self._attempting:
                raise DispatchDeferred("reentrant execution is forbidden")
            if self._uncertain:
                raise DispatchUncertain("execution outcome requires reconciliation")
            if self._issued:
                if len(self._issued) != 1 or self._issued_observation is None:
                    raise DispatchUncertain("invalid issued lease inventory")
                permit = next(iter(self._issued.values()))
                if token_budget < permit.tokens:
                    raise DispatchDeferred("requested budget cannot cover pending permit")
                self._validate_pending(permit)
                self._issued_budget = token_budget
                return (permit,), self._issued_observation
            return self.plan_live(token_budget=token_budget)

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
        an execution without authenticated durable output or a rolled-back anchor.
        """
        from .fair_stream_execution_journal import (
            ExecutionOutcomeUnknown, FairStreamExecutionJournal,
        )
        from .fair_stream_recovery import (
            RecoveryAuthorization, verify_recovery_authorization,
        )

        if type(journal) is not FairStreamExecutionJournal:
            raise ValueError("canonical committed execution journal required")
        self._require_owner_process()
        with self._lock:
            if self._attempting:
                raise DispatchDeferred("active execution prevents reconciliation")
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
                from .fair_stream_execution_journal import JournaledExecutionOwner
                from .fair_stream_result_vault import SealedFairStreamResultVault

                owner = self._owner
                if (type(owner) is JournaledExecutionOwner
                        and type(owner._backend) is SealedFairStreamResultVault):
                    if owner._journal is not journal or not owner.whole_request:
                        raise ExecutionOutcomeUnknown("recovery must use the bound whole-request owner")
                    rows = checkpoint["requests"]
                    matching = [r for r in rows if r["request_id"] == permit.request_id]
                    if len(matching) != 1 or matching[0]["remaining_tokens"] != permit.tokens:
                        raise ExecutionOutcomeUnknown("partial native lease cannot be reconciled as terminal")
                    receipt = journal.reconcile_sealed_completion(permit, vault=owner._backend)
                else:
                    receipt = journal.recover_committed_receipt(permit)
                updated = self._session.acknowledge(receipt)
            except BaseException as exc:
                # SQLite I/O errors, interruption and malformed receipts are
                # also uncertain outcomes. Do not leave the app reporting an
                # apparently healthy executor after a failed reconciliation.
                self._uncertain = True
                raise DispatchUncertain(
                    "committed receipt unavailable or custody reconciliation failed"
                ) from exc
            self._issued.clear()
            self._issued_budget = None
            self._issued_observation = None
            self._uncertain = False
            return updated

    def abandon_uncertain(self, *, authorization: object, recovery_key: bytes) -> dict[str, object]:
        """Operator-only recovery for a stopped whole-request native executor.

        The distinct approval attests quiescence; it cannot prove it. Stop
        other owners before this operation. No result is created or discarded.
        """
        from .fair_stream_execution_journal import JournaledExecutionOwner
        from .fair_stream_result_vault import SealedFairStreamResultVault
        from .fair_stream_recovery import verify_abandonment_authorization

        self._require_owner_process()
        with self._lock:
            if self._attempting:
                raise DispatchDeferred("active execution prevents abandonment")
            owner = self._owner
            if (type(owner) is not JournaledExecutionOwner or not owner.whole_request
                    or type(owner._backend) is not SealedFairStreamResultVault
                    or owner._journal._private_handle is None):
                raise DispatchUncertain("bound private native owner required for abandonment")
            state = self._session.verify()
            pending = state["checkpoint"]["pending"]
            if len(pending) != 1:
                raise DispatchUncertain("exactly one pending lease required")
            lease = pending[0]
            permit = DispatchPermit(lease["lease_id"], lease["request_id"], state["generation"],
                                    state["checkpoint_digest"], lease["tokens"], lease["bytes_reserved"])
            if self._issued and self._issued.get(permit.lease_id) != permit:
                raise DispatchUncertain("in-memory lease differs from durable custody")
            verify_abandonment_authorization(authorization, recovery_key=recovery_key,
                                             state=state, lease_id=permit.lease_id)
            try:
                owner._backend.assert_no_published_result(permit)
                receipt = owner._journal.record_abandonment(
                    permit, evidence_digest=authorization.evidence_digest,
                )
                # A prior worker that still publishes after approval is a
                # violated quiescence assumption; retain the lease on discovery.
                owner._backend.assert_no_published_result(permit)
                if self._revoke_queued_prompt is not None:
                    self._revoke_queued_prompt(permit.request_id)
                # Reauthorize the stopped guard only for the signed retired
                # lease, while dispatch is still serialized. If the custody
                # CAS fails, the pending lease continues to block all planning.
                from .native_fair_stream_backend import NativeFairStreamBackend

                native = owner._backend._backend
                if type(native) is not NativeFairStreamBackend:
                    raise DispatchUncertain("canonical native pressure owner required")
                native.reauthorize_retired_lease(permit)
                updated = self._session.abandon(receipt)
            except BaseException as exc:
                self._uncertain = True
                raise DispatchUncertain("abandonment requires trusted reconciliation") from exc
            self._issued.clear()
            self._issued_budget = None
            self._issued_observation = None
            self._uncertain = False
            return updated

    def execute_once(self, permit: DispatchPermit) -> dict[str, object]:
        """Execute at most once, with a fresh OS re-probe and signed receipt.

        If the backend raises, a result may already have been committed. The
        permit remains pending and this adapter refuses automatic retry.
        """
        with self._execution_attempt():
            if self._uncertain:
                raise DispatchUncertain("execution outcome requires reconciliation")
            state = self._validate_pending(permit)
            # Re-probe the raw requested budget, not the already derated lease.
            if self._issued_budget is None:
                raise DispatchUncertain("missing issued pressure budget")
            budget, observation = self._sample(self._issued_budget)
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
            try:
                receipt = self._owner.execute_and_commit(permit, refreshed)
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
            self._issued_budget = None
            self._issued_observation = None
            self._last_execution_observation = observation
            return updated
