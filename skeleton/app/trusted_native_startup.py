"""Explicit, in-process native startup with trusted application-owned authorities.

Not a public configuration loader, not a distributed deployment proof.
Pass this object directly to create_app(trusted_protected_bootstrap=...).
No HTTP request, environment value or model output can create a trust anchor.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any

from skeleton.ai.runtime.inference.native_guard_binding import (
    NativeGuardPins, make_pinned_native_guard_factory,
)
from skeleton.ai.runtime.inference.signed_reviewer_client import SignedReviewerClient
from skeleton.app.compose_guarded_preflight import (
    _authenticated_principals, _database_name, _trusted_topology,
)
from skeleton.context.sealed_sandwich import SealedContextBoundaryError
from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, verify_canonical_source_writer_inventory,
)


class NativeStartupBlocked(RuntimeError):
    """Trusted native startup dependencies cannot establish their custody."""


class _UnboundSnapshot:
    async def resolve(self, **kwargs):
        raise SealedContextBoundaryError("canonical execution snapshot reader not installed")


def _pin_digest(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value))


def _namespace(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 128:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch in "_.-") for ch in value)


def _validate_layout(epoch: MongoCanonicalSourceEpoch, conversation: Any, memory: Any) -> None:
    # Until a separate writer-custody protocol is qualified, do not infer
    # identical physical deployment from matching URI/database strings.
    database = getattr(epoch, "_database", None)
    name = getattr(database, "name", None)
    client = getattr(database, "client", None)
    if not _database_name(name) or client is None:
        raise NativeStartupBlocked("canonical epoch database identity unavailable")
    bindings = (
        (epoch, "_collection", "canonical_source_epochs"),
        (epoch, "_reader", "canonical_source_epochs"),
        (conversation, "threads", "conversation_threads"),
        (conversation, "messages", "conversation_messages"),
        (memory, "records", "canonical_memory_records"),
        (memory, "idempotency", "canonical_memory_idempotency"),
        (memory, "revisions", "canonical_memory_revisions"),
        (memory, "projection_outbox", "canonical_memory_projection_outbox"),
    )
    for owner, attribute, expected_name in bindings:
        collection = getattr(owner, attribute, None)
        collection_name = getattr(collection, "name", None)
        owning_database = getattr(collection, "database", None)
        actual_db_name = getattr(owning_database, "name", None)
        if (type(collection_name) is not str or collection_name != expected_name
                or type(actual_db_name) is not str or actual_db_name != name
                or getattr(owning_database, "client", None) is not client):
            raise NativeStartupBlocked("canonical source collection ownership mismatch")
    verify_canonical_source_writer_inventory(conversation=conversation, memory=memory, epoch=epoch)


async def _observe_primary(epoch: MongoCanonicalSourceEpoch) -> tuple:
    db = epoch._database
    async with asyncio.timeout(5):
        before = _trusted_topology(await db.command("hello"))
        authentication = await db.command("connectionStatus")
        users = _authenticated_principals(authentication)
        after = _trusted_topology(await db.command("hello"))
    if before is None or before != after or users is None:
        raise NativeStartupBlocked("authenticated stable Mongo primary required")
    # Explicit nonempty role inventory is mandatory here. The observation
    # still cannot demonstrate all external writers have been retired.
    info = authentication["authInfo"]
    roles = info.get("authenticatedUserRoles")
    if type(roles) is not list or not roles:
        raise NativeStartupBlocked("authenticated Mongo role inventory required")
    return before, users


@dataclass(frozen=True, slots=True)
class TrustedNativeStartup:
    """Deployer-constructed composition for the actual canonical native registry.

    All dependencies belong to the trusted deployer. Caller is responsible for
    closing externally owned DB client/reviewer after the ASGI service drains.
    Does not provision epochs, select or download a model, or mutate Mongo.
    """

    conversation: Any
    memory: Any
    epoch: MongoCanonicalSourceEpoch
    reviewer: SignedReviewerClient
    pins: tuple[NativeGuardPins, ...]
    policy_sha256: str
    memory_namespace: str

    def __post_init__(self) -> None:
        if type(self.epoch) is not MongoCanonicalSourceEpoch:
            raise NativeStartupBlocked("canonical source epoch required")
        if not _pin_digest(self.policy_sha256) or not _namespace(self.memory_namespace):
            raise NativeStartupBlocked("independent policy and memory namespace pins required")
        if (type(self.reviewer) is not SignedReviewerClient
                or getattr(self.reviewer, "_closed", True) is not False):
            raise NativeStartupBlocked("live independently pinned reviewer required")
        if (type(self.pins) is not tuple or not 1 <= len(self.pins) <= 32
                or any(type(pin) is not NativeGuardPins for pin in self.pins)
                or len(set(pin.model_id for pin in self.pins)) != len(self.pins)):
            raise NativeStartupBlocked("unique independently reviewed native model pins required")

    async def __call__(self, state: Any) -> None:
        from skeleton.api.server import ServerState

        if type(state) is not ServerState:
            raise NativeStartupBlocked("canonical server startup state required")
        if (state.engine_execution_service is not None
                or state.engine_execution_coordinator is not None
                or state._engine_shutdown_pending
                or state._engine_local_guard_components is not None
                or getattr(state, "_engine_canonical_sources", None) is not None
                or getattr(state, "_engine_canonical_mongo_owners", None) is not None):
            raise NativeStartupBlocked("native startup must precede service construction")
        try:
            _validate_layout(self.epoch, self.conversation, self.memory)
            initial = await _observe_primary(self.epoch)
            components = make_pinned_native_guard_factory(
                snapshots=_UnboundSnapshot(), reviewer=self.reviewer, pins=self.pins,
            )
            final = await _observe_primary(self.epoch)
            if initial != final or getattr(self.reviewer, "_closed", True) is not False:
                raise NativeStartupBlocked("native startup authority changed")
            _validate_layout(self.epoch, self.conversation, self.memory)
            state.configure_engine_protected_native_startup(
                components=components, conversation=self.conversation,
                memory=self.memory, shared_epoch=self.epoch,
                memory_namespace=self.memory_namespace, policy_sha256=self.policy_sha256,
            )
        except NativeStartupBlocked:
            raise
        except Exception:
            raise NativeStartupBlocked("trusted native startup authority unavailable") from None


__all__ = ["NativeStartupBlocked", "TrustedNativeStartup"]
