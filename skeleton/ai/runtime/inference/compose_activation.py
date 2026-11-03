"""Fail-closed activation barrier for Compose-hosted native local inference.

This barrier does not initialize Mongo, migrate existing volumes, manufacture a
reviewer, or turn a standalone mongod into a replica set. It is deliberately
unusable until the operator has supplied a primary-backed canonical source
epoch, fenced owners, and an independently administered reviewer. Inference
remains unavailable on any ambiguous or stale observation.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch,
    MongoSourceEpochError,
    verify_canonical_source_writer_inventory,
)
from skeleton.provider_runtime import ProviderPolicyError

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PROBE_SECONDS = 5.0


class ActivationBlocked(ProviderPolicyError):
    """Protected inference cannot establish or retain its startup authority."""


class ActivationPhase(str, Enum):
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class ActivationPermit:
    """Single-generation evidence, not a bearer token or reusable capability."""

    generation: int
    tenant_id: str
    actor_id: str
    context_id: str
    epoch: int
    model_digest: str
    runtime_digest: str
    tokenizer_digest: str


class MongoGuardedActivation:
    """Owner-scoped barrier with exact native artifact and Mongo epoch binding.

    A production composition root must supply the SAME Mongo database object
    used to construct the epoch and install that epoch on both canonical owners.
    A known-method inventory is checked, but external writers, replica-set
    membership and reviewer independence still require operational assurance.
    This object is not a replacement for the pre-delivery adversarial guard.
    """

    def __init__(
        self, *,
        database: Any,
        epoch: MongoCanonicalSourceEpoch,
        conversation: Any,
        memory: Any,
        backend: Any,
        reviewer: Any,
        reviewer_authority_id: str,
        tenant_id: str,
        actor_id: str,
        context_id: str,
        expected_model_digest: str,
        expected_runtime_digest: str,
        expected_tokenizer_digest: str,
    ) -> None:
        from .native_transformer import NativeTransformerModel

        if type(epoch) is not MongoCanonicalSourceEpoch:
            raise ActivationBlocked("canonical Mongo epoch authority required")
        if getattr(epoch, "_database", None) is not database:
            raise ActivationBlocked("activation must use the canonical epoch database")
        if type(backend) is not NativeTransformerModel:
            raise ActivationBlocked("exact activated native transformer required")
        if not callable(reviewer) or reviewer is backend:
            raise ActivationBlocked("independent reviewer must be injected by application")
        if (not isinstance(reviewer_authority_id, str)
                or not 1 <= len(reviewer_authority_id) <= 128
                or reviewer_authority_id != reviewer_authority_id.strip()
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in reviewer_authority_id)):
            raise ActivationBlocked("reviewer authority identity invalid")
        for value in (tenant_id, actor_id, context_id):
            if (not isinstance(value, str) or not value or value != value.strip()
                    or len(value.encode("utf-8", errors="strict")) > 512
                    or any(ord(ch) < 32 for ch in value)):
                raise ActivationBlocked("activation owner scope invalid")
        for value in (expected_model_digest, expected_runtime_digest, expected_tokenizer_digest):
            if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
                raise ActivationBlocked("activated artifact digest invalid")
        if not callable(getattr(database, "command", None)):
            raise ActivationBlocked("Mongo replica-set authority unavailable")
        self._database = database
        self._epoch = epoch
        self._conversation = conversation
        self._memory = memory
        self._backend = backend
        self._reviewer = reviewer
        self._reviewer_authority_id = reviewer_authority_id
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._context_id = context_id
        self._identity = (
            expected_model_digest, expected_runtime_digest, expected_tokenizer_digest,
        )
        self._phase = ActivationPhase.BLOCKED
        self._generation = 0
        self._epoch_at_activation: int | None = None
        self._lock = asyncio.Lock()

    @property
    def phase(self) -> ActivationPhase:
        return self._phase

    def _verify_backend(self) -> None:
        try:
            backend = self._backend
            backend.assert_identity()
            tokenizer = backend.runtime.tokenizer
            tokenizer.assert_unchanged()
            current = (backend.model_digest, backend.runtime_digest, tokenizer.digest)
            if current != self._identity:
                raise ActivationBlocked("activated model or tokenizer changed")
        except ActivationBlocked:
            raise
        except Exception:
            raise ActivationBlocked("native model/tokenizer identity unavailable") from None

    async def _probe(self) -> int:
        try:
            async with asyncio.timeout(_MAX_PROBE_SECONDS):
                hello = await self._database.command("hello")
            if (type(hello) is not dict
                    or not isinstance(hello.get("setName"), str)
                    or not hello["setName"]
                    or hello.get("isWritablePrimary") is not True):
                raise ActivationBlocked("linearizable Mongo replica-set primary required")
            # The backend and engine may use different logical databases on
            # the same Mongo server. A seqlock in one database does not fence
            # canonical writes in another database or another client.
            db_name = getattr(self._database, "name", None)
            db_client = getattr(self._database, "client", None)
            if not isinstance(db_name, str) or not db_name or db_client is None:
                raise ActivationBlocked("canonical Mongo database identity missing")
            collections = (
                getattr(self._epoch, "_collection", None),
                getattr(self._epoch, "_reader", None),
                getattr(self._conversation, "threads", None),
                getattr(self._conversation, "messages", None),
                getattr(self._memory, "records", None),
                getattr(self._memory, "idempotency", None),
                getattr(self._memory, "revisions", None),
                getattr(self._memory, "projection_outbox", None),
            )
            for collection in collections:
                owner = getattr(collection, "database", None)
                if (getattr(owner, "name", None) != db_name
                        or getattr(owner, "client", None) is not db_client):
                    raise ActivationBlocked("canonical source database ownership mismatch")
            verify_canonical_source_writer_inventory(
                conversation=self._conversation, memory=self._memory, epoch=self._epoch,
            )
            self._verify_backend()
            return await self._epoch.read_epoch(
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
                context_id=self._context_id,
            )
        except ActivationBlocked:
            raise
        except (MongoSourceEpochError, TimeoutError):
            raise ActivationBlocked("canonical source epoch unavailable") from None
        except Exception:
            raise ActivationBlocked("protected activation authority unavailable") from None

    async def activate(self) -> ActivationPermit:
        """Explicit startup; never provisions an epoch or performs migration."""
        async with self._lock:
            if self._phase is ActivationPhase.REVOKED:
                raise ActivationBlocked("revoked activation cannot restart in place")
            self._phase = ActivationPhase.VERIFYING
            self._generation += 1
            generation = self._generation
            try:
                epoch = await self._probe()
            except BaseException:
                self._phase = ActivationPhase.BLOCKED
                self._epoch_at_activation = None
                raise
            self._epoch_at_activation = epoch
            self._phase = ActivationPhase.ACTIVE
            return ActivationPermit(
                generation, self._tenant_id, self._actor_id, self._context_id,
                epoch, *self._identity,
            )

    async def assert_active(self, permit: ActivationPermit | None = None) -> ActivationPermit:
        """Revalidate before dispatch AND after generation, including revocations.

        A stable epoch change also blocks inference: even a legitimate writer
        changes the canonical source and needs a fresh explicit activation.
        """
        async with self._lock:
            if self._phase is not ActivationPhase.ACTIVE:
                raise ActivationBlocked("guarded local inference is not activated")
            generation = self._generation
            epoch_at_activation = self._epoch_at_activation
            expected = ActivationPermit(
                generation, self._tenant_id, self._actor_id, self._context_id,
                epoch_at_activation, *self._identity,
            )
            if permit is not None and (type(permit) is not ActivationPermit or permit != expected):
                raise ActivationBlocked("activation permit is stale or mismatched")
        try:
            epoch = await self._probe()
        except BaseException:
            async with self._lock:
                if self._phase is ActivationPhase.ACTIVE:
                    self._phase = ActivationPhase.BLOCKED
                    self._generation += 1
                    self._epoch_at_activation = None
            raise
        async with self._lock:
            if (self._phase is not ActivationPhase.ACTIVE
                    or self._generation != generation
                    or self._epoch_at_activation != epoch
                    or epoch != epoch_at_activation):
                # A concurrent operator revocation is terminal, not a
                # recoverable BLOCKED state that activate() may later reset.
                if self._phase is ActivationPhase.ACTIVE:
                    self._phase = ActivationPhase.BLOCKED
                self._generation += 1
                self._epoch_at_activation = None
                raise ActivationBlocked("canonical authority changed during inference")
            return expected

    async def revoke(self) -> None:
        """Local irrevocable hold. Global revocation needs an audited Mongo write."""
        async with self._lock:
            self._phase = ActivationPhase.REVOKED
            self._generation += 1
            self._epoch_at_activation = None



async def compose_mongo_guarded_native_adapter(
    runtime: Any, *,
    database: Any,
    epoch: MongoCanonicalSourceEpoch,
    conversation: Any,
    memory: Any,
    snapshots: Any,
    reviewer: Any,
    reviewer_authority_id: str,
    tenant_id: str,
    actor_id: str,
    context_id: str,
    model_id: str = "skeleton-native-transformer",
    cache_size: int = 128,
    default_seed: int = 0,
    max_concurrency: int = 1,
    max_queue_size: int = 256,
    max_batch_size: int = 256,
):
    """Build an activated, guarded native adapter; never create an unguarded one.

    This is a trusted application composition entrypoint, NOT a client-facing
    API. The caller must already have provisioned Mongo replica-set custody,
    independently reviewed writer coverage and a trusted reviewer. The factory
    refuses to provision epochs, modify Compose or silently select a model.
    """
    from .native_transformer import NativeTransformerModel
    from .native_guard_binding import native_transformer_guard_components
    from .guarded_composition import compose_protected_local_adapter
    from .local import LocalInferenceEngine

    backend = NativeTransformerModel(runtime, model_id=model_id)
    gate = MongoGuardedActivation(
        database=database, epoch=epoch, conversation=conversation, memory=memory,
        backend=backend, reviewer=reviewer,
        reviewer_authority_id=reviewer_authority_id,
        tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
        expected_model_digest=backend.model_digest,
        expected_runtime_digest=backend.runtime_digest,
        expected_tokenizer_digest=backend.runtime.tokenizer.digest,
    )
    await gate.activate()
    try:
        components = native_transformer_guard_components(
            backend, snapshots=snapshots, reviewer=reviewer,
        )
        engine = LocalInferenceEngine(
            backend, cache_size=cache_size, max_concurrency=max_concurrency,
            max_queue_size=max_queue_size, max_batch_size=max_batch_size,
            require_guarded_context=True,
        )
        return compose_protected_local_adapter(
            engine, components=components, default_seed=default_seed,
            activation_gate=gate,
            artifact_status={
                "kind": "native_transformer",
                "model_digest": backend.model_digest,
                "runtime_digest": backend.runtime_digest,
                "tokenizer_digest": backend.runtime.tokenizer.digest,
                "architecture_digest": runtime.architecture.digest,
                "device": runtime.device.to_dict(),
                "generation_limits": backend.generation_limits(),
            },
        )
    except BaseException:
        # An incomplete composition must not leave a live activation.
        await gate.revoke()
        raise

__all__ = [
    "ActivationBlocked", "ActivationPhase", "ActivationPermit", "MongoGuardedActivation",
    "compose_mongo_guarded_native_adapter",
]
