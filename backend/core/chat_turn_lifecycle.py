"""Live product-chat lifecycle over the durable AI-chat turn authority.

This coordinator does not own transcript data, model execution, or tool
execution. It binds the existing product route to the durable turn journal and
provides idempotent forward progression for the normal chat path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.ai.assistant.turn_ownership import (
    TurnLeasePolicy,
    TurnLeaseToken,
    TurnOwnershipReceipt,
)
from skeleton.ai.assistant.turn_runtime import (
    FailureClass,
    TERMINAL_STATES,
    TurnState,
    make_event,
)
from skeleton.persistence.chat_turn_repository import (
    ChatTurnBinding,
    ChatTurnNotFound,
    PersistedChatTurn,
)


_ROUTE_STAGES = (
    TurnState.RECEIVED,
    TurnState.ADMITTED,
    TurnState.USER_MESSAGE_COMMITTED,
    TurnState.CONTEXT_COMPILING,
    TurnState.ROUTING,
    TurnState.MODEL_RUNNING,
    TurnState.VERIFYING,
    TurnState.FINALIZING,
    TurnState.ASSISTANT_MESSAGE_COMMITTED,
    TurnState.COMPLETE,
)
_STAGE_INDEX = {state: index for index, state in enumerate(_ROUTE_STAGES)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ChatTurnLifecycle:
    """Idempotent normal-path coordination around one durable turn authority."""

    authority: Any

    async def begin(
        self,
        *,
        thread,
        user_message,
        operation_id: str,
        request_digest: str,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn:
        existing = await self.get_if_present(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if existing is not None:
            if (
                existing.snapshot.request_digest != request_digest
                or existing.binding.thread_id != thread.thread_id
                or existing.binding.causal_user_message_id != user_message.message_id
                or existing.binding.tenant_id != tenant_id
                or existing.binding.owner_id != owner_id
            ):
                raise ValueError(
                    "existing durable turn does not match canonical retry identity"
                )
            turn = existing
        else:
            binding = ChatTurnBinding.from_conversation(thread, user_message)
            turn = await self.authority.create_operation(
                operation_id=operation_id,
                request_digest=request_digest,
                binding=binding,
                created_at=user_message.created_at,
            )
        return await self.advance(
            turn,
            TurnState.USER_MESSAGE_COMMITTED,
            tenant_id=tenant_id,
            owner_id=owner_id,
            reason_code="conversation-user-committed",
        )

    async def acquire_execution(
        self,
        turn: PersistedChatTurn,
        *,
        tenant_id: str,
        owner_id: str,
        holder_id: str,
        ttl_seconds: float | None = None,
        policy: TurnLeasePolicy | None = None,
    ) -> TurnLeaseToken:
        return await self.authority.acquire_lease(
            turn.snapshot.operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            holder_id=holder_id,
            ttl_seconds=ttl_seconds,
            policy=policy,
        )

    async def renew_execution(
        self,
        lease: TurnLeaseToken,
        *,
        ttl_seconds: float | None = None,
        policy: TurnLeasePolicy | None = None,
    ) -> TurnLeaseToken:
        return await self.authority.renew_lease(
            lease,
            ttl_seconds=ttl_seconds,
            policy=policy,
        )

    async def release_execution(
        self,
        lease: TurnLeaseToken,
    ) -> TurnOwnershipReceipt:
        return await self.authority.release_lease(lease)

    async def get_if_present(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn | None:
        try:
            return await self.authority.get_operation(
                operation_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
            )
        except ChatTurnNotFound:
            return None

    async def advance(
        self,
        turn: PersistedChatTurn,
        target: TurnState,
        *,
        tenant_id: str,
        owner_id: str,
        reason_code: str,
        provider_receipt_ref: str | None = None,
        lease: TurnLeaseToken | None = None,
    ) -> PersistedChatTurn:
        current = turn.snapshot.state
        if current in TERMINAL_STATES:
            return turn
        if current is target:
            return turn
        if current not in _STAGE_INDEX or target not in _STAGE_INDEX:
            raise ValueError(
                f"route lifecycle cannot linearly advance {current.value} -> {target.value}"
            )
        current_index = _STAGE_INDEX[current]
        target_index = _STAGE_INDEX[target]
        if current_index > target_index:
            return turn

        result = turn
        for state in _ROUTE_STAGES[current_index + 1 : target_index + 1]:
            event = make_event(
                result.snapshot,
                state,
                observed_at=_now(),
                reason_code=reason_code,
                provider_receipt_ref=(
                    provider_receipt_ref
                    if state is TurnState.VERIFYING
                    else None
                ),
            )
            append_kwargs = {
                "tenant_id": tenant_id,
                "owner_id": owner_id,
            }
            if lease is not None:
                append_kwargs["lease"] = lease
            result = await self.authority.append_event(
                event,
                **append_kwargs,
            )
        return result

    async def fail(
        self,
        turn: PersistedChatTurn,
        *,
        tenant_id: str,
        owner_id: str,
        reason_code: str,
        retryable: bool = False,
        cancelled: bool = False,
        lease: TurnLeaseToken | None = None,
    ) -> PersistedChatTurn:
        if turn.snapshot.state in TERMINAL_STATES:
            return turn
        if cancelled:
            target = TurnState.CANCELLED
            failure = FailureClass.CANCELLED
        elif retryable:
            target = TurnState.FAILED_RETRYABLE
            failure = FailureClass.RETRYABLE
        else:
            target = TurnState.FAILED_TERMINAL
            failure = FailureClass.TERMINAL
        event = make_event(
            turn.snapshot,
            target,
            observed_at=_now(),
            reason_code=reason_code,
            failure_class=failure,
        )
        append_kwargs = {
            "tenant_id": tenant_id,
            "owner_id": owner_id,
        }
        if lease is not None:
            append_kwargs["lease"] = lease
        return await self.authority.append_event(
            event,
            **append_kwargs,
        )

    async def finalize_existing_assistant(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ) -> PersistedChatTurn | None:
        turn = await self.get_if_present(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if turn is None or turn.snapshot.state in TERMINAL_STATES:
            return turn
        return await self.advance(
            turn,
            TurnState.COMPLETE,
            tenant_id=tenant_id,
            owner_id=owner_id,
            reason_code="conversation-assistant-already-committed",
        )


__all__ = ["ChatTurnLifecycle"]
