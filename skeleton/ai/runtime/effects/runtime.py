"""Governed assembled AI -> effect -> verify -> learn execution plane."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Sequence
from uuid import NAMESPACE_URL, uuid5

from .contracts import (
    BatchState,
    CommittedEffect,
    CoreExecution,
    EffectAuthorization,
    EffectBatchResult,
    EffectExecutionReceipt,
    EffectProposal,
    ensure_aware,
    utc_now,
)
from .decoder import ProposalSource
from .ledger import SQLiteEffectLedger
from .policy import AuthorizationProvider, EffectPolicy
from .registry import EffectContext, EffectHandlerRegistry


class AICore(Protocol):
    async def run(self, request: Any) -> CoreExecution: ...


class EffectCommitSink(Protocol):
    async def commit(
        self,
        result: EffectBatchResult,
    ) -> None: ...


@dataclass(slots=True)
class NullCommitSink:
    async def commit(
        self,
        result: EffectBatchResult,
    ) -> None:
        return None


class EffectRuntimeError(RuntimeError):
    pass


class GovernedEffectRuntime:
    def __init__(
        self,
        *,
        core: AICore,
        proposal_source: ProposalSource,
        authorizer: AuthorizationProvider,
        registry: EffectHandlerRegistry,
        ledger: SQLiteEffectLedger,
        policy: EffectPolicy | None = None,
        memory_sink: EffectCommitSink | None = None,
        learning_sink: EffectCommitSink | None = None,
        worker_id: str = "effects.runtime",
    ) -> None:
        self.core = core
        self.proposal_source = proposal_source
        self.authorizer = authorizer
        self.registry = registry
        self.ledger = ledger
        self.policy = policy or EffectPolicy()
        self.memory_sink = memory_sink or NullCommitSink()
        self.learning_sink = learning_sink or NullCommitSink()
        self.worker_id = worker_id

    async def execute(
        self,
        request: Any,
        *,
        subject_id: str,
        dry_run: bool = False,
        deadline: datetime | None = None,
    ) -> EffectBatchResult:
        if deadline is not None:
            deadline = ensure_aware(
                deadline,
                "deadline",
            )
            if utc_now() >= deadline:
                raise EffectRuntimeError(
                    "effect deadline already expired"
                )

        core = await self.core.run(request)
        proposals = tuple(
            await self.proposal_source.proposals(core)
        )
        if any(
            p.operation_id != core.operation_id
            or p.tenant_id != core.tenant_id
            for p in proposals
        ):
            raise EffectRuntimeError(
                "proposal escaped core operation/tenant identity"
            )
        self.policy.validate(proposals)

        tx_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "effect-batch:"
                    + core.execution_id
                    + ":"
                    + ":".join(p.digest for p in proposals)
                ),
            )
        )
        created = self.ledger.begin_transaction(
            transaction_id=tx_id,
            tenant_id=core.tenant_id,
            operation_id=core.operation_id,
            core_execution_id=core.execution_id,
            core_evidence_digest=core.evidence_digest,
        )
        if not created:
            state = self.ledger.transaction_state(tx_id)
            if state == BatchState.COMMITTED.value:
                return EffectBatchResult(
                    transaction_id=tx_id,
                    state=BatchState.COMMITTED,
                    core=core,
                    effects=(),
                    reason="replayed committed effect batch",
                    replayed=True,
                    event_chain_digest=self.ledger.verify_chain(
                        tx_id
                    ),
                )
            raise EffectRuntimeError(
                "existing nonterminal effect transaction: "
                f"{state}"
            )

        for proposal in proposals:
            self.ledger.record_proposal(
                tx_id,
                proposal,
            )

        if not proposals:
            self.ledger.set_transaction_state(
                tx_id,
                BatchState.COMMITTED.value,
                reason="no effects proposed",
            )
            result = EffectBatchResult(
                transaction_id=tx_id,
                state=BatchState.COMMITTED,
                core=core,
                reason="no effects proposed",
                event_chain_digest=self.ledger.verify_chain(
                    tx_id
                ),
            )
            await self.memory_sink.commit(result)
            await self.learning_sink.commit(result)
            return result

        if dry_run:
            self.ledger.set_transaction_state(
                tx_id,
                BatchState.DRY_RUN.value,
                reason=(
                    "dry-run; no authorization or effects"
                ),
            )
            return EffectBatchResult(
                transaction_id=tx_id,
                state=BatchState.DRY_RUN,
                core=core,
                reason="dry-run",
                event_chain_digest=self.ledger.verify_chain(
                    tx_id
                ),
            )

        self.ledger.claim(
            tx_id,
            self.worker_id,
        )
        try:
            self.ledger.set_transaction_state(
                tx_id,
                BatchState.AUTHORIZING.value,
            )
            now = utc_now()
            authorizations: list[EffectAuthorization] = []
            rejected: list[str] = []

            for proposal in proposals:
                self._check_deadline(deadline)
                try:
                    auth = await self.authorizer.authorize(
                        proposal,
                        subject_id=subject_id,
                        now=now,
                    )
                except Exception as exc:
                    reason = (
                        "authorization failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    self.ledger.set_transaction_state(
                        tx_id,
                        BatchState.FAILED.value,
                        reason=reason,
                    )
                    return EffectBatchResult(
                        transaction_id=tx_id,
                        state=BatchState.FAILED,
                        core=core,
                        reason=reason,
                        event_chain_digest=(
                            self.ledger.verify_chain(tx_id)
                        ),
                    )

                if (
                    auth.proposal_digest != proposal.digest
                    or auth.subject_id != subject_id
                ):
                    reason = (
                        "authorization identity/digest mismatch"
                    )
                    self.ledger.set_transaction_state(
                        tx_id,
                        BatchState.FAILED.value,
                        reason=reason,
                    )
                    return EffectBatchResult(
                        transaction_id=tx_id,
                        state=BatchState.FAILED,
                        core=core,
                        reason=reason,
                        event_chain_digest=(
                            self.ledger.verify_chain(tx_id)
                        ),
                    )

                if not auth.permits(
                    proposal,
                    subject_id=subject_id,
                    now=now,
                ):
                    rejected.append(
                        proposal.proposal_id
                    )
                    self.ledger.update_proposal(
                        tx_id,
                        proposal.digest,
                        state="rejected",
                        authorization=auth.as_dict(),
                        event_type="proposal.denied",
                        event_payload={
                            "reason": auth.reason
                        },
                    )
                else:
                    authorizations.append(auth)
                    self.ledger.update_proposal(
                        tx_id,
                        proposal.digest,
                        state="authorized",
                        authorization=auth.as_dict(),
                        event_type="proposal.authorized",
                        event_payload={
                            "authorization_id": (
                                auth.authorization_id
                            )
                        },
                    )

            if rejected:
                self.ledger.set_transaction_state(
                    tx_id,
                    BatchState.REJECTED.value,
                    reason=(
                        "one or more proposals denied"
                    ),
                )
                return EffectBatchResult(
                    transaction_id=tx_id,
                    state=BatchState.REJECTED,
                    core=core,
                    rejected_proposal_ids=tuple(
                        rejected
                    ),
                    reason="authorization denied",
                    event_chain_digest=(
                        self.ledger.verify_chain(tx_id)
                    ),
                )

            self.ledger.set_transaction_state(
                tx_id,
                BatchState.AUTHORIZED.value,
            )
            committed: list[CommittedEffect] = []
            applied: list[
                tuple[
                    EffectProposal,
                    EffectAuthorization,
                    EffectExecutionReceipt,
                ]
            ] = []
            context = EffectContext(
                transaction_id=tx_id,
                subject_id=subject_id,
                deadline=deadline,
            )
            self.ledger.set_transaction_state(
                tx_id,
                BatchState.APPLYING.value,
            )

            for proposal, auth in zip(
                proposals,
                authorizations,
                strict=True,
            ):
                self._check_deadline(deadline)
                self.ledger.update_proposal(
                    tx_id,
                    proposal.digest,
                    state="applying",
                )
                try:
                    receipt = await self.registry.apply(
                        proposal,
                        context,
                    )
                except Exception as exc:
                    return await self._rollback(
                        tx_id,
                        core,
                        context,
                        applied,
                        reason=(
                            "apply failed: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                        in_doubt_proposal=proposal,
                    )

                self.ledger.update_proposal(
                    tx_id,
                    proposal.digest,
                    state="applied",
                    execution=receipt.as_dict(),
                    event_type="proposal.applied",
                    event_payload={
                        "execution_digest": (
                            receipt.digest
                        )
                    },
                )
                applied.append(
                    (proposal, auth, receipt)
                )
                self.ledger.set_transaction_state(
                    tx_id,
                    BatchState.VERIFYING.value,
                )

                try:
                    verification = (
                        await self.registry.verify(
                            proposal,
                            receipt,
                            context,
                        )
                    )
                except Exception as exc:
                    return await self._rollback(
                        tx_id,
                        core,
                        context,
                        applied,
                        reason=(
                            "verification failed: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )

                self.ledger.update_proposal(
                    tx_id,
                    proposal.digest,
                    state=(
                        "verified"
                        if verification.passed
                        else "verification_failed"
                    ),
                    verification=verification.as_dict(),
                    event_type="proposal.verified",
                    event_payload={
                        "passed": verification.passed,
                        "verification_digest": (
                            verification.digest
                        ),
                    },
                )
                if not verification.passed:
                    return await self._rollback(
                        tx_id,
                        core,
                        context,
                        applied,
                        reason=(
                            "postcondition verification "
                            "failed: "
                            f"{verification.reason}"
                        ),
                    )

                committed.append(
                    CommittedEffect(
                        proposal,
                        auth,
                        receipt,
                        verification,
                    )
                )
                self.ledger.set_transaction_state(
                    tx_id,
                    BatchState.APPLYING.value,
                )

            self.ledger.set_transaction_state(
                tx_id,
                BatchState.COMMITTED.value,
            )
            result = EffectBatchResult(
                transaction_id=tx_id,
                state=BatchState.COMMITTED,
                core=core,
                effects=tuple(committed),
                reason=(
                    "all effects independently verified"
                ),
                event_chain_digest=(
                    self.ledger.verify_chain(tx_id)
                ),
            )
            # Memory and learning observe committed
            # evidence only; they never authorize it.
            await self.memory_sink.commit(result)
            await self.learning_sink.commit(result)
            return result
        finally:
            try:
                self.ledger.release(
                    tx_id,
                    self.worker_id,
                )
            except Exception:
                pass

    def _check_deadline(
        self,
        deadline: datetime | None,
    ) -> None:
        if (
            deadline is not None
            and utc_now() >= deadline
        ):
            raise EffectRuntimeError(
                "effect deadline expired"
            )

    async def _rollback(
        self,
        tx_id: str,
        core: CoreExecution,
        context: EffectContext,
        applied: Sequence[
            tuple[
                EffectProposal,
                EffectAuthorization,
                EffectExecutionReceipt,
            ]
        ],
        *,
        reason: str,
        in_doubt_proposal: EffectProposal | None = None,
    ) -> EffectBatchResult:
        self.ledger.set_transaction_state(
            tx_id,
            BatchState.ROLLING_BACK.value,
            reason=reason,
        )
        rolled_back: list[str] = []
        uncompensated: list[str] = (
            []
            if in_doubt_proposal is None
            else [in_doubt_proposal.proposal_id]
        )
        if in_doubt_proposal is not None:
            self.ledger.update_proposal(
                tx_id,
                in_doubt_proposal.digest,
                state="in_doubt",
                event_type="proposal.in_doubt",
                event_payload={"reason": reason},
            )

        for proposal, _auth, receipt in reversed(
            tuple(applied)
        ):
            if not proposal.reversible:
                uncompensated.append(
                    proposal.proposal_id
                )
                continue
            try:
                self.ledger.update_proposal(
                    tx_id,
                    proposal.digest,
                    state="compensating",
                )
                outcome = (
                    await self.registry.compensate(
                        proposal,
                        receipt,
                        context,
                    )
                )
            except Exception as exc:
                uncompensated.append(
                    proposal.proposal_id
                )
                self.ledger.append_event(
                    tx_id,
                    "proposal.compensation_failed",
                    {
                        "proposal_digest": (
                            proposal.digest
                        ),
                        "error": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    },
                )
                continue

            if outcome.compensated:
                rolled_back.append(
                    proposal.proposal_id
                )
                self.ledger.update_proposal(
                    tx_id,
                    proposal.digest,
                    state="rolled_back",
                    event_type=(
                        "proposal.rolled_back"
                    ),
                    event_payload={
                        "executor_id": (
                            outcome.executor_id
                        )
                    },
                )
            else:
                uncompensated.append(
                    proposal.proposal_id
                )

        final_state = (
            BatchState.PARTIAL_FAILURE
            if uncompensated
            else BatchState.ROLLED_BACK
        )
        self.ledger.set_transaction_state(
            tx_id,
            final_state.value,
            reason=reason,
        )
        suffix = (
            ""
            if not uncompensated
            else (
                "; uncompensated="
                + ",".join(uncompensated)
            )
        )
        return EffectBatchResult(
            transaction_id=tx_id,
            state=final_state,
            core=core,
            rolled_back_proposal_ids=tuple(
                rolled_back
            ),
            reason=reason + suffix,
            event_chain_digest=(
                self.ledger.verify_chain(tx_id)
            ),
        )
