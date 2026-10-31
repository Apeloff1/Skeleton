"""Fail-closed pre/postflight facade over Skeleton's canonical local inference engine.

Production composition MUST use a trusted reader that derives snapshots from
authorized conversation state, an independent reviewer, the actual backend
tokenizer and native sampler constraints. This interface never promotes a
client-supplied root or a model's own review into authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from skeleton.context.pre_delivery_guard import (
    DeliveryContract,
    GuardedLocalInference,
    PreDeliveryReceipt,
    TrustedContextSnapshot,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextReplayError,
)


class TrustedSnapshotReader(Protocol):
    """Resolve an independently authorized canonical snapshot, not user metadata."""

    async def resolve(
        self, *, tenant_scope_id: str, context_id: str, request_digest: str
    ) -> TrustedContextSnapshot: ...


@dataclass(frozen=True, slots=True)
class GuardedGeneration:
    result: Any
    receipt: PreDeliveryReceipt
    canonical_snapshot_version: int


class CanonicalGuardedLocalService:
    """Local inference with mandatory admission and double-checked authority.

    The app's composition root must route protected operations to this facade
    rather than invoking the unguarded LocalInferenceEngine.generate path.
    """

    def __init__(
        self, guard: GuardedLocalInference, *, snapshots: TrustedSnapshotReader,
    ) -> None:
        if not isinstance(guard, GuardedLocalInference) or not callable(
            getattr(snapshots, "resolve", None)
        ):
            raise SealedContextError("guard and authoritative snapshot reader required")
        self.guard = guard
        self.snapshots = snapshots

    async def _read(
        self, *, tenant_scope_id: str, context_id: str, request_digest: str
    ) -> TrustedContextSnapshot:
        snapshot = await self.snapshots.resolve(
            tenant_scope_id=tenant_scope_id, context_id=context_id,
            request_digest=request_digest,
        )
        if not isinstance(snapshot, TrustedContextSnapshot):
            raise SealedContextBoundaryError("snapshot reader returned unverified state")
        if snapshot.tenant_id != tenant_scope_id or snapshot.context_id != context_id:
            raise SealedContextBoundaryError("snapshot reader crossed authorized scope")
        return snapshot

    async def generate(
        self, request: Any, *, tenant_scope_id: str, context_id: str,
        contract: DeliveryContract = DeliveryContract(), **engine_options: Any,
    ) -> GuardedGeneration:
        if (
            not isinstance(tenant_scope_id, str) or not tenant_scope_id
            or not isinstance(context_id, str) or not context_id
            or not isinstance(contract, DeliveryContract)
        ):
            raise SealedContextBoundaryError("canonical guard scope or contract missing")
        if any(key in engine_options for key in (
            "snapshot", "tenant_scope_id", "contract", "prepared_input",
        )):
            raise SealedContextBoundaryError("caller attempted to override guarded authority")
        digest = getattr(request, "digest", None)
        if not isinstance(digest, str) or not digest:
            raise SealedContextError("request needs a deterministic input digest")
        before = await self._read(
            tenant_scope_id=tenant_scope_id, context_id=context_id,
            request_digest=digest,
        )
        result, receipt = await self.guard.generate(
            request, snapshot=before, tenant_scope_id=tenant_scope_id,
            contract=contract, **engine_options,
        )
        # Local model generation happened, but no answer has been released.
        # Reject concurrent edits, revocations and policy/version changes.
        after = await self._read(
            tenant_scope_id=tenant_scope_id, context_id=context_id,
            request_digest=digest,
        )
        if after != before:
            raise SealedContextReplayError("canonical context changed during local inference")
        return GuardedGeneration(result, receipt, after.snapshot_version)
