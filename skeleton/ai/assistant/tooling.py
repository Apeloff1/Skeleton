"""Bounded, idempotent capability execution for assistant tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
from typing import Awaitable, Callable, Mapping

from .capabilities import CapabilityAuthorizer, CapabilityRegistry
from .contracts import (
    AssistantRequest,
    CapabilityGrant,
    SideEffectClass,
    ToolProposal,
    ToolReceipt,
    digest_json,
)


class ToolCoordinatorError(RuntimeError):
    """The assistant tool loop cannot continue safely."""


CapabilityHandler = Callable[
    [Mapping[str, object]],
    Mapping[str, object] | Awaitable[Mapping[str, object]],
]


@dataclass(frozen=True, slots=True)
class ToolRunResult:
    receipt: ToolReceipt
    output: Mapping[str, object] | None
    replayed: bool = False


class ToolCoordinator:
    """Execute registered capabilities under request-bound authority and budgets."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        authorizer: CapabilityAuthorizer | None = None,
    ) -> None:
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("registry must be CapabilityRegistry")
        self.registry = registry
        self.authorizer = authorizer or CapabilityAuthorizer()
        self._handlers: dict[str, CapabilityHandler] = {}
        self._receipts: dict[str, tuple[str, ToolRunResult]] = {}
        self._request_call_counts: dict[str, int] = {}

    def bind(self, capability_id: str, handler: CapabilityHandler) -> None:
        descriptor = self.registry.get(capability_id)
        if not callable(handler):
            raise TypeError("handler must be callable")
        existing = self._handlers.get(descriptor.capability_id)
        if existing is not None and existing is not handler:
            raise ValueError(
                f"handler for {descriptor.capability_id!r} cannot be silently replaced"
            )
        self._handlers[descriptor.capability_id] = handler

    @staticmethod
    def _proposal_binding(proposal: ToolProposal) -> str:
        return digest_json(
            {
                "proposal_id": proposal.proposal_id,
                "capability_id": proposal.capability_id,
                "arguments": dict(proposal.arguments),
                "request_digest": proposal.request_digest,
                "side_effect": proposal.side_effect.value,
                "idempotency_key": proposal.idempotency_key,
            }
        )

    async def execute(
        self,
        proposal: ToolProposal,
        request: AssistantRequest,
        *,
        grants: tuple[CapabilityGrant, ...] = (),
        explicit_user_action: bool = False,
        requested_scopes: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> ToolRunResult:
        if proposal.request_digest != request.digest:
            raise ToolCoordinatorError("proposal is bound to a different request")

        descriptor = self.registry.get(proposal.capability_id)
        if descriptor.side_effect is not proposal.side_effect:
            raise ToolCoordinatorError("proposal side-effect classification mismatch")

        binding = self._proposal_binding(proposal)
        prior = self._receipts.get(proposal.idempotency_key)
        if prior is not None:
            prior_binding, result = prior
            if prior_binding != binding:
                raise ToolCoordinatorError(
                    "idempotency key was reused for a different proposal"
                )
            return ToolRunResult(
                receipt=result.receipt,
                output=result.output,
                replayed=True,
            )

        instant = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
        decision = self.authorizer.decide(
            descriptor,
            request,
            grants=grants,
            requested_scopes=requested_scopes,
            explicit_user_action=explicit_user_action,
            now=instant,
        )
        if not decision.allowed:
            receipt = ToolReceipt(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                status="blocked",
                output_ref=None,
                request_digest=request.digest,
                arguments_digest=proposal.arguments_digest,
                started_at=instant,
                finished_at=instant,
                error_code=decision.reason_code,
                provenance=("assistant-capability-authorizer",),
            )
            return ToolRunResult(receipt=receipt, output=None)

        count = self._request_call_counts.get(request.digest, 0)
        if count >= request.max_tool_calls:
            receipt = ToolReceipt(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                status="blocked",
                output_ref=None,
                request_digest=request.digest,
                arguments_digest=proposal.arguments_digest,
                started_at=instant,
                finished_at=instant,
                error_code="tool-call-budget-exhausted",
                provenance=("assistant-tool-budget",),
            )
            return ToolRunResult(receipt=receipt, output=None)

        handler = self._handlers.get(proposal.capability_id)
        if handler is None:
            raise ToolCoordinatorError(
                f"no handler bound for {proposal.capability_id!r}"
            )

        self._request_call_counts[request.digest] = count + 1
        started = instant
        try:
            value = handler(proposal.arguments)
            if inspect.isawaitable(value):
                value = await value
            if not isinstance(value, Mapping):
                raise ToolCoordinatorError("capability output must be a mapping")
            output = dict(value)
            encoded = json.dumps(
                output,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if len(encoded) > descriptor.max_output_bytes:
                raise ToolCoordinatorError("capability output exceeds declared bound")
            supplied_ref = output.get("output_ref")
            output_ref = (
                str(supplied_ref).strip()
                if isinstance(supplied_ref, str) and supplied_ref.strip()
                else "assistant-tool-output:" + digest_json(output)
            )
            finished = datetime.now(timezone.utc)
            receipt = ToolReceipt(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                status="succeeded",
                output_ref=output_ref,
                request_digest=request.digest,
                arguments_digest=proposal.arguments_digest,
                started_at=started,
                finished_at=finished,
                provenance=(
                    "assistant-tool-coordinator",
                    f"capability:{proposal.capability_id}",
                ),
            )
            result = ToolRunResult(receipt=receipt, output=output)
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            receipt = ToolReceipt(
                proposal_id=proposal.proposal_id,
                capability_id=proposal.capability_id,
                status="failed",
                output_ref=None,
                request_digest=request.digest,
                arguments_digest=proposal.arguments_digest,
                started_at=started,
                finished_at=finished,
                error_code=type(exc).__name__,
                provenance=(
                    "assistant-tool-coordinator",
                    f"capability:{proposal.capability_id}",
                ),
            )
            result = ToolRunResult(receipt=receipt, output=None)

        self._receipts[proposal.idempotency_key] = (binding, result)
        return result

    def reset_request_budget(self, request_digest: str) -> None:
        self._request_call_counts.pop(request_digest, None)


__all__ = [
    "CapabilityHandler",
    "ToolCoordinator",
    "ToolCoordinatorError",
    "ToolRunResult",
]
