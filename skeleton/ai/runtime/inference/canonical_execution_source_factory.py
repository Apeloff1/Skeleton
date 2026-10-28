"""Execution-scoped canonical source authority for production local-provider admission.

Application startup registers an operator-owned binding resolver; it must read
its own committed execution->conversation authorization, not provider metadata.
Every prepare, guarded admission and postflight reloads the canonical owners.
No global per-request mutable pointer or caller-controlled thread selector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from skeleton.context.sealed_sandwich import SealedContextBoundaryError

from .canonical_owner_source_loader import CanonicalOwnerSourceCollectionLoader
from .canonical_source_custody import CanonicalSegmentSourceAuthority


@dataclass(frozen=True, slots=True)
class AuthorizedExecutionConversation:
    execution_id: str
    tenant_id: str
    actor_id: str
    context_id: str
    thread_id: str
    revoked: bool = False


class CanonicalExecutionConversationResolver(Protocol):
    async def resolve(
        self, *, execution_id: str, tenant_id: str, actor_id: str,
        context_id: str,
    ) -> AuthorizedExecutionConversation: ...


class _ScopedExecutionOwnerLoader:
    def __init__(self, *, execution_id: str, factory: "CanonicalExecutionSourceFactory"):
        self._execution_id = execution_id
        self._factory = factory

    async def read_current(self, *, tenant_id: str, actor_id: str, context_id: str):
        try:
            binding = await self._factory.resolver.resolve(
                execution_id=self._execution_id, tenant_id=tenant_id,
                actor_id=actor_id, context_id=context_id,
            )
        except Exception as exc:
            raise SealedContextBoundaryError("execution conversation binding unavailable") from exc
        if (type(binding) is not AuthorizedExecutionConversation
                or binding.revoked is not False
                or (binding.execution_id, binding.tenant_id, binding.actor_id,
                    binding.context_id) !=
                   (self._execution_id, tenant_id, actor_id, context_id)
                or not isinstance(binding.thread_id, str) or not binding.thread_id):
            raise SealedContextBoundaryError("execution conversation authorization was revoked")
        loader = CanonicalOwnerSourceCollectionLoader(
            conversation=self._factory.conversation, tenant_id=tenant_id,
            actor_id=actor_id, context_id=context_id,
            thread_id=binding.thread_id, purpose=self._factory.purpose,
            memory=self._factory.memory,
            memory_namespace=self._factory.memory_namespace,
            shared_epoch=self._factory.shared_epoch,
        )
        return await loader.read_current(
            tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
        )


class CanonicalExecutionSourceFactory:
    """Application-owned execution binding to actual current source owners."""

    def __init__(
        self, *, conversation: Any, resolver: CanonicalExecutionConversationResolver,
        memory: Any | None = None, memory_namespace: str | None = None,
        shared_epoch: Any | None = None, purpose: str = "model-inference",
    ) -> None:
        if not callable(getattr(resolver, "resolve", None)):
            raise SealedContextBoundaryError("independent execution conversation resolver required")
        # Mixed-owner sources are admissible only if BOTH canonical writer
        # objects are actively configured with the SAME shared epoch. A
        # detached read-only callback cannot certify all writer paths.
        if memory is not None and (
            shared_epoch is None
            or getattr(conversation, "canonical_source_epoch", None) is not shared_epoch
            or getattr(memory, "canonical_source_epoch", None) is not shared_epoch
        ):
            raise SealedContextBoundaryError(
                "canonical conversation and memory writers must share the durable epoch"
            )
        # Validate actual owner APIs and mixed-source epoch requirements at
        # composition rather than waiting for the first model request.
        CanonicalOwnerSourceCollectionLoader(
            conversation=conversation,
            tenant_id="startup-validation", actor_id="startup-validation",
            context_id="startup-validation", thread_id="startup-validation",
            purpose=purpose, memory=memory,
            memory_namespace=memory_namespace, shared_epoch=shared_epoch,
        )
        self.conversation = conversation
        self.resolver = resolver
        self.memory = memory
        self.memory_namespace = memory_namespace
        self.shared_epoch = shared_epoch
        self.purpose = purpose

    def bind_execution(self, execution_id: str) -> CanonicalSegmentSourceAuthority:
        if (not isinstance(execution_id, str) or not execution_id
                or execution_id != execution_id.strip()
                or len(execution_id) > 512):
            raise SealedContextBoundaryError("durable execution identifier required")
        return CanonicalSegmentSourceAuthority(
            loader=_ScopedExecutionOwnerLoader(execution_id=execution_id, factory=self),
        )


__all__ = [
    "AuthorizedExecutionConversation", "CanonicalExecutionConversationResolver",
    "CanonicalExecutionSourceFactory",
]
