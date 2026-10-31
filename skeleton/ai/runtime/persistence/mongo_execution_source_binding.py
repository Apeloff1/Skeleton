"""Derive an execution's actual conversation from canonical stored user commands.

No new mapping collection is created. A protected engine request must bind to
the existing MongoConversationAuthority's durable _chat_engine_command record
at its exact handoff.turn_id. The owner validates the stored command digest,
thread, user message, tenant, actor and canonical immutable engine identity.
Missing, edited, regenerated or deleted references fail closed.
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
    """Application-owned reader over the ORIGINAL canonical conversation command."""

    def __init__(self, *, conversation: Any, engine_service: Any) -> None:
        if (not callable(getattr(conversation, "get_thread", None))
                or not callable(getattr(conversation, "user_engine_command", None))
                or not callable(getattr(getattr(conversation, "messages", None), "find_one", None))
                or not callable(getattr(getattr(engine_service, "submissions", None),
                                        "get_by_execution_id", None))
                or not callable(getattr(getattr(engine_service, "repository", None), "get", None))):
            raise SealedContextBoundaryError("canonical conversation and engine owners required")
        self._conversation = conversation
        self._engine_service = engine_service

    async def resolve(
        self, *, execution_id: str, tenant_id: str, actor_id: str,
        context_id: str,
    ) -> AuthorizedExecutionConversation:
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
                or not isinstance(handoff.turn_id, str)
                or not handoff.turn_id
            ):
                raise SealedContextBoundaryError("engine execution is no longer authorized")
            # The chat authority generated this user message ID; only its
            # current committed source document is allowed to resolve a thread.
            document = await self._conversation.messages.find_one({
                "_id": handoff.turn_id, "author_type": "user",
            })
            if not isinstance(document, dict):
                raise SealedContextBoundaryError("canonical user message missing")
            thread_id = document.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise SealedContextBoundaryError("canonical user thread identity invalid")
            thread = await self._conversation.get_thread(
                thread_id, tenant_id=tenant_id, owner_id=actor_id,
            )
            if (thread.state is not ConversationThreadState.ACTIVE
                    or thread.thread_id != thread_id):
                raise SealedContextBoundaryError("canonical conversation inactive or revoked")
            actual = await self._conversation.user_engine_command(
                thread_id, handoff.turn_id,
                tenant_id=tenant_id, owner_id=actor_id,
            )
            # The conversation owner validates the command's own persisted
            # bytes and SHA-256 digest before returning it. The engine owner
            # has independently persisted another exact command: equality
            # anchors the two durable owners to ONE execution identity.
            if actual is None or actual != command.as_dict():
                raise SealedContextBoundaryError("conversation engine command differs from execution")
            return AuthorizedExecutionConversation(
                execution_id, tenant_id, actor_id, context_id, thread_id,
            )
        except SealedContextBoundaryError:
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("canonical execution source binding unavailable") from exc


__all__ = ["MongoExecutionConversationResolver"]
