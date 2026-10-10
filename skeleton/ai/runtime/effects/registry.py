"""Effect execution and independent verification registry."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from .contracts import (
    ApplyResult,
    CompensationResult,
    EffectExecutionReceipt,
    EffectProposal,
    EffectVerificationReceipt,
    VerificationResult,
    utc_now,
)


class EffectRegistryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EffectContext:
    transaction_id: str
    subject_id: str
    deadline: datetime | None = None


def _execution_timeout(
    proposal: EffectProposal,
    context: EffectContext,
) -> float:
    timeout = proposal.timeout_ms / 1000
    if context.deadline is None:
        return timeout
    remaining = (context.deadline - utc_now()).total_seconds()
    if remaining <= 0:
        raise TimeoutError("effect deadline expired")
    return min(timeout, remaining)


class EffectHandler(Protocol):
    handler_id: str

    async def apply(
        self,
        proposal: EffectProposal,
        context: EffectContext,
    ) -> ApplyResult: ...

    async def compensate(
        self,
        proposal: EffectProposal,
        receipt: EffectExecutionReceipt,
        context: EffectContext,
    ) -> CompensationResult: ...


class EffectVerifier(Protocol):
    verifier_id: str

    async def verify(
        self,
        proposal: EffectProposal,
        receipt: EffectExecutionReceipt,
        context: EffectContext,
    ) -> VerificationResult: ...


@dataclass(slots=True)
class CallbackEffectHandler:
    handler_id: str
    apply_fn: Callable[
        [EffectProposal, EffectContext],
        Awaitable[ApplyResult],
    ]
    compensate_fn: Callable[
        [EffectProposal, EffectExecutionReceipt, EffectContext],
        Awaitable[CompensationResult],
    ]

    async def apply(
        self,
        proposal: EffectProposal,
        context: EffectContext,
    ) -> ApplyResult:
        return await self.apply_fn(proposal, context)

    async def compensate(
        self,
        proposal: EffectProposal,
        receipt: EffectExecutionReceipt,
        context: EffectContext,
    ) -> CompensationResult:
        return await self.compensate_fn(
            proposal,
            receipt,
            context,
        )


@dataclass(slots=True)
class CallbackEffectVerifier:
    verifier_id: str
    verify_fn: Callable[
        [EffectProposal, EffectExecutionReceipt, EffectContext],
        Awaitable[VerificationResult],
    ]

    async def verify(
        self,
        proposal: EffectProposal,
        receipt: EffectExecutionReceipt,
        context: EffectContext,
    ) -> VerificationResult:
        return await self.verify_fn(
            proposal,
            receipt,
            context,
        )


class EffectHandlerRegistry:
    def __init__(self) -> None:
        self._entries: dict[
            str,
            tuple[EffectHandler, EffectVerifier],
        ] = {}

    def register(
        self,
        kind: str,
        *,
        handler: EffectHandler,
        verifier: EffectVerifier,
    ) -> None:
        if kind in self._entries:
            raise EffectRegistryError(
                f"handler already registered for {kind}"
            )
        if handler.handler_id == verifier.verifier_id:
            raise EffectRegistryError(
                "executor and verifier identities must differ"
            )
        self._entries[kind] = (handler, verifier)

    def entry(
        self,
        kind: str,
    ) -> tuple[EffectHandler, EffectVerifier]:
        try:
            return self._entries[kind]
        except KeyError as exc:
            raise EffectRegistryError(
                f"no handler for effect kind {kind}"
            ) from exc

    async def apply(
        self,
        proposal: EffectProposal,
        context: EffectContext,
    ) -> EffectExecutionReceipt:
        handler, _ = self.entry(proposal.kind)
        started = utc_now()
        result = await asyncio.wait_for(
            handler.apply(proposal, context),
            timeout=_execution_timeout(proposal, context),
        )
        if result.executor_id != handler.handler_id:
            raise EffectRegistryError(
                "handler returned mismatched executor identity"
            )
        completed = utc_now()
        return EffectExecutionReceipt(
            receipt_id=str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        "effect-receipt:"
                        f"{context.transaction_id}:"
                        f"{proposal.digest}"
                    ),
                )
            ),
            proposal_digest=proposal.digest,
            executor_id=result.executor_id,
            status=result.status,
            started_at=started,
            completed_at=completed,
            output=result.output,
            compensation_token=result.compensation_token,
            evidence_refs=result.evidence_refs,
        )

    async def verify(
        self,
        proposal: EffectProposal,
        receipt: EffectExecutionReceipt,
        context: EffectContext,
    ) -> EffectVerificationReceipt:
        handler, verifier = self.entry(proposal.kind)
        if handler.handler_id == verifier.verifier_id:
            raise EffectRegistryError(
                "verification must be independent from execution"
            )
        result = await asyncio.wait_for(
            verifier.verify(
                proposal,
                receipt,
                context,
            ),
            timeout=_execution_timeout(proposal, context),
        )
        if result.verifier_id != verifier.verifier_id:
            raise EffectRegistryError(
                "verifier returned mismatched identity"
            )
        declared = {
            pc.name: pc.required
            for pc in proposal.postconditions
        }
        for name, required in declared.items():
            if (
                required
                and result.postconditions.get(name) is not True
            ):
                return EffectVerificationReceipt(
                    proposal_digest=proposal.digest,
                    execution_digest=receipt.digest,
                    verifier_id=result.verifier_id,
                    passed=False,
                    postconditions=result.postconditions,
                    observed=result.observed,
                    reason=(
                        "required postcondition failed: "
                        f"{name}"
                    ),
                    verified_at=utc_now(),
                    evidence_refs=result.evidence_refs,
                )
        return EffectVerificationReceipt(
            proposal_digest=proposal.digest,
            execution_digest=receipt.digest,
            verifier_id=result.verifier_id,
            passed=bool(result.passed),
            postconditions=result.postconditions,
            observed=result.observed,
            reason=result.reason,
            verified_at=utc_now(),
            evidence_refs=result.evidence_refs,
        )

    async def compensate(
        self,
        proposal: EffectProposal,
        receipt: EffectExecutionReceipt,
        context: EffectContext,
    ) -> CompensationResult:
        handler, _ = self.entry(proposal.kind)
        # Compensation is safety cleanup and remains bounded by the
        # proposal timeout, not by an already-expired user deadline.
        return await asyncio.wait_for(
            handler.compensate(
                proposal,
                receipt,
                context,
            ),
            timeout=proposal.timeout_ms / 1000,
        )
