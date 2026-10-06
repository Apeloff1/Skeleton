"""Live product-chat lifecycle over the durable AI-chat turn authority.

This coordinator does not own transcript data, model execution, or tool
execution. It binds the existing product route to the durable turn journal and
provides idempotent forward progression for the normal chat path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from skeleton.ai.assistant.turn_runtime import (
    FailureClass,
    TERMINAL_STATES,
    TurnState,
    make_event,
    provider_receipt_set_ref,
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

    @staticmethod
    def _provider_binding_matches(
        actual: str | None,
        receipt_refs: tuple[str, ...],
    ) -> bool:
        expected = provider_receipt_set_ref(receipt_refs)
        if actual == expected:
            return True
        normalized = tuple(
            dict.fromkeys(ref.strip() for ref in receipt_refs)
        )
        return len(normalized) == 1 and actual == normalized[0]

    @classmethod
    def assert_provider_receipts(
        cls,
        turn: PersistedChatTurn,
        provider_receipt_refs: Iterable[str],
    ) -> str | None:
        refs = tuple(provider_receipt_refs)
        expected = provider_receipt_set_ref(refs)
        if not cls._provider_binding_matches(
            turn.snapshot.provider_receipt_ref,
            refs,
        ):
            raise ValueError(
                "durable provider receipt binding does not match "
                "canonical assistant message"
            )
        return expected

    async def advance(
        self,
        turn: PersistedChatTurn,
        target: TurnState,
        *,
        tenant_id: str,
        owner_id: str,
        reason_code: str,
        provider_receipt_ref: str | None = None,
        provider_receipt_refs: Iterable[str] | None = None,
    ) -> PersistedChatTurn:
        refs = (
            None
            if provider_receipt_refs is None
            else tuple(provider_receipt_refs)
        )
        canonical_receipt_ref = (
            None
            if refs is None
            else provider_receipt_set_ref(refs)
        )
        if (
            provider_receipt_ref is not None
            and canonical_receipt_ref is not None
            and provider_receipt_ref != canonical_receipt_ref
        ):
            raise ValueError(
                "provider receipt ref conflicts with canonical receipt-set binding"
            )
        effective_receipt_ref = (
            canonical_receipt_ref
            if refs is not None
            else provider_receipt_ref
        )
        if (
            refs is not None
            and turn.snapshot.provider_receipt_ref is not None
            and not self._provider_binding_matches(
                turn.snapshot.provider_receipt_ref,
                refs,
            )
        ):
            raise ValueError("provider receipt binding drifted across turn stages")
        if (
            refs is None
            and effective_receipt_ref is not None
            and turn.snapshot.provider_receipt_ref not in {
                None,
                effective_receipt_ref,
            }
        ):
            raise ValueError("provider receipt binding drifted across turn stages")

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
            bind_receipt = (
                effective_receipt_ref
                if effective_receipt_ref is not None
                and result.snapshot.provider_receipt_ref is None
                else None
            )
            event = make_event(
                result.snapshot,
                state,
                observed_at=_now(),
                reason_code=reason_code,
                provider_receipt_ref=bind_receipt,
            )
            result = await self.authority.append_event(
                event,
                tenant_id=tenant_id,
                owner_id=owner_id,
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
        return await self.authority.append_event(
            event,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    async def finalize_existing_assistant(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        provider_receipt_refs: Iterable[str] = (),
    ) -> PersistedChatTurn | None:
        turn = await self.get_if_present(
            operation_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        if turn is None or turn.snapshot.state in TERMINAL_STATES:
            return turn
        refs = tuple(provider_receipt_refs)
        turn = await self.advance(
            turn,
            TurnState.COMPLETE,
            tenant_id=tenant_id,
            owner_id=owner_id,
            reason_code="conversation-assistant-already-committed",
            provider_receipt_refs=refs,
        )
        self.assert_provider_receipts(turn, refs)
        return turn


__all__ = ["ChatTurnLifecycle"]
