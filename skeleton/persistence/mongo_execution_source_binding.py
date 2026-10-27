"""Majority-backed canonical conversation binding for protected engine executions.

This is an index into existing durable engine and conversation ownership, not
an alternative conversation authority. Only authenticated server dispatch
may register a binding after the engine submission has been durably accepted.
Neither a provider request nor a compiled source snapshot may mint it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from skeleton.ai.runtime.inference.canonical_execution_source_factory import (
    AuthorizedExecutionConversation,
)
from skeleton.context.sealed_sandwich import SealedContextBoundaryError
from skeleton.contracts.conversation import ConversationThreadState


class MongoExecutionConversationResolver:
    """Read current scoped conversation ownership plus persisted dispatch link."""

    def __init__(self, *, conversation: Any, engine_service: Any) -> None:
        if (not callable(getattr(conversation, "get_thread", None))
                or not callable(getattr(getattr(engine_service, "submissions", None),
                                        "get_by_execution_id", None))
                or not callable(getattr(getattr(engine_service, "repository", None),
                                        "get", None))):
            raise SealedContextBoundaryError("canonical conversation and engine owners required")
        database = getattr(conversation, "database", None)
        if not callable(getattr(database, "get_collection", None)):
            raise SealedContextBoundaryError("Mongo canonical conversation database required")
        try:
            from pymongo.read_concern import ReadConcern
            from pymongo.write_concern import WriteConcern
            self._bindings = database.get_collection(
                "conversation_execution_source_bindings",
                read_concern=ReadConcern("majority"),
                write_concern=WriteConcern(w="majority", wtimeout=10000),
            )
        except Exception as exc:
            raise SealedContextBoundaryError("majority-backed execution binding unavailable") from exc
        self._conversation = conversation
        self._engine_service = engine_service

    async def _engine_binding(
        self, *, execution_id: str, tenant_id: str, actor_id: str, context_id: str,
    ) -> None:
        try:
            stored, execution = await asyncio.to_thread(
                lambda: (
                    self._engine_service.submissions.get_by_execution_id(execution_id),
                    self._engine_service.repository.get(execution_id),
                )
            )
            if stored is None or execution is None:
                raise SealedContextBoundaryError("canonical execution does not exist")
            command = stored.command
            handoff = command.compiled_context
            operation = command.operation
            if (
                handoff.execution_id != execution_id
                or handoff.context_id != context_id
                or handoff.tenant_id != tenant_id
                or operation.actor_id != actor_id
                or operation.tenant_id != tenant_id
                or execution.request.execution_id != execution_id
                or execution.operation_id != operation.operation_id
                or execution.cancellation_requested
                or execution.terminal
                or command.execution_request.identity_digest
                   != execution.request.identity_digest
            ):
                raise SealedContextBoundaryError("engine execution is no longer authorized")
        except SealedContextBoundaryError:
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("durable engine source identity unavailable") from exc

    async def register(
        self, *, execution_id: str, tenant_id: str, actor_id: str,
        context_id: str, thread_id: str,
    ) -> AuthorizedExecutionConversation:
        """Trusted dispatch must register this BEFORE model work starts."""
        await self._engine_binding(
            execution_id=execution_id, tenant_id=tenant_id,
            actor_id=actor_id, context_id=context_id,
        )
        try:
            thread = await self._conversation.get_thread(
                thread_id, tenant_id=tenant_id, owner_id=actor_id,
            )
            if (thread.state is not ConversationThreadState.ACTIVE
                    or thread.thread_id != thread_id):
                raise SealedContextBoundaryError("conversation not active")
            payload = {
                "_id": execution_id, "tenant_id": tenant_id,
                "actor_id": actor_id, "context_id": context_id,
                "thread_id": thread_id, "revoked": False,
            }
            try:
                await self._bindings.insert_one(payload)
            except Exception:
                # Exact replay is idempotent; rebind/retarget is forbidden.
                current = await self._bindings.find_one({"_id": execution_id})
                if not isinstance(current, dict) or any(
                    current.get(key) != value for key, value in payload.items()
                ):
                    raise SealedContextBoundaryError(
                        "execution conversation binding cannot be overwritten"
                    )
            return AuthorizedExecutionConversation(
                execution_id, tenant_id, actor_id, context_id, thread_id,
            )
        except SealedContextBoundaryError:
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("canonical execution registration unavailable") from exc

    async def resolve(
        self, *, execution_id: str, tenant_id: str, actor_id: str,
        context_id: str,
    ) -> AuthorizedExecutionConversation:
        await self._engine_binding(
            execution_id=execution_id, tenant_id=tenant_id,
            actor_id=actor_id, context_id=context_id,
        )
        try:
            entry = await self._bindings.find_one({
                "_id": execution_id, "tenant_id": tenant_id,
                "actor_id": actor_id, "context_id": context_id, "revoked": False,
            })
            if (not isinstance(entry, dict)
                    or not isinstance(entry.get("thread_id"), str)
                    or not entry["thread_id"]):
                raise SealedContextBoundaryError("execution conversation binding unavailable")
            thread = await self._conversation.get_thread(
                entry["thread_id"], tenant_id=tenant_id, owner_id=actor_id,
            )
            if (thread.state is not ConversationThreadState.ACTIVE
                    or thread.thread_id != entry["thread_id"]):
                raise SealedContextBoundaryError("canonical conversation was revoked")
            return AuthorizedExecutionConversation(
                execution_id, tenant_id, actor_id, context_id, thread.thread_id,
            )
        except SealedContextBoundaryError:
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("canonical execution owner unavailable") from exc


__all__ = ["MongoExecutionConversationResolver"]
