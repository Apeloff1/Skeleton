"""Assistant capability policy over Skeleton's canonical tool runtime.

The assistant layer may select and authorize capabilities, but it is not a
second execution authority. Every admitted call is translated into the
canonical ToolExecutionRequest contract and delegated to AsyncToolRuntime,
which owns argument validation, approval binding, metering, idempotency
fencing, and durable receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
from typing import Awaitable, Callable, Mapping
from uuid import NAMESPACE_URL, uuid5

from skeleton.skills.tool_contract import (
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
    approval_ref_for_request,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime, ToolNotFound

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
    """The assistant capability loop cannot continue safely."""


CapabilityHandler = Callable[
    [Mapping[str, object]],
    Mapping[str, object] | Awaitable[Mapping[str, object]],
]


@dataclass(frozen=True, slots=True)
class ToolRunResult:
    receipt: ToolReceipt
    output: Mapping[str, object] | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class _BoundCapability:
    manifest: ToolManifest
    handler: CapabilityHandler
    canonical_handler: Callable[[ToolExecutionRequest], Awaitable[str | None]]


_EFFECT_MAP = {
    SideEffectClass.NONE: ToolEffect.READ_ONLY,
    SideEffectClass.READ_ONLY: ToolEffect.READ_ONLY,
    SideEffectClass.REVERSIBLE_WRITE: ToolEffect.REVERSIBLE,
    SideEffectClass.EXTERNAL_WRITE: ToolEffect.IRREVERSIBLE,
    SideEffectClass.SECURITY_SENSITIVE: ToolEffect.IRREVERSIBLE,
}


def _canonical_operation_id(request: AssistantRequest) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-assistant-operation:" + request.digest,
        )
    )


def _canonical_request_id(binding: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-assistant-tool-request:" + binding,
        )
    )


class ToolCoordinator:
    """Authorize assistant capabilities and delegate execution canonically.

    ToolCoordinator deliberately owns no tool receipt implementation and never
    invokes capability side effects directly. Production composition should
    inject the application's shared AsyncToolRuntime with a durable receipt
    store and admission runtime. The default remains the same canonical runtime
    type so isolated tests and library consumers do not acquire a separate
    execution contract.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        authorizer: CapabilityAuthorizer | None = None,
        tool_runtime: AsyncToolRuntime | None = None,
    ) -> None:
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("registry must be CapabilityRegistry")
        if tool_runtime is not None and not isinstance(tool_runtime, AsyncToolRuntime):
            raise TypeError("tool_runtime must be AsyncToolRuntime")
        self.registry = registry
        self.authorizer = authorizer or CapabilityAuthorizer()
        self.tool_runtime = tool_runtime or AsyncToolRuntime()
        self._bindings: dict[str, _BoundCapability] = {}
        self._idempotency_bindings: dict[tuple[str, str], str] = {}
        self._request_call_counts: dict[str, int] = {}
        self._outputs: dict[tuple[str, str, str], Mapping[str, object]] = {}

    def bind(self, capability_id: str, handler: CapabilityHandler) -> None:
        """Bind product I/O while leaving execution authority canonical."""

        descriptor = self.registry.get(capability_id)
        if not callable(handler):
            raise TypeError("handler must be callable")
        existing = self._bindings.get(descriptor.capability_id)
        if existing is not None:
            if existing.handler is not handler:
                raise ValueError(
                    f"handler for {descriptor.capability_id!r} cannot be silently replaced"
                )
            return

        manifest = ToolManifest(
            tool_id=descriptor.capability_id,
            version="assistant-v1",
            description=(
                "Assistant capability delegated through the canonical Skeleton "
                f"tool runtime: {descriptor.kind.value}"
            ),
            input_schema={
                "type": "object",
                "additionalProperties": True,
            },
            effect=_EFFECT_MAP[descriptor.side_effect],
            approval_required=descriptor.requires_explicit_user_action,
        )

        async def canonical_handler(
            canonical_request: ToolExecutionRequest,
            *,
            _handler: CapabilityHandler = handler,
            _descriptor=descriptor,
        ) -> str | None:
            value = _handler(canonical_request.arguments)
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
            if len(encoded) > _descriptor.max_output_bytes:
                raise ToolCoordinatorError("capability output exceeds declared bound")
            supplied_ref = output.get("output_ref")
            output_ref = (
                str(supplied_ref).strip()
                if isinstance(supplied_ref, str) and supplied_ref.strip()
                else "assistant-tool-output:" + digest_json(output)
            )
            key = (
                canonical_request.tenant_id,
                canonical_request.operation_id,
                canonical_request.idempotency_key,
            )
            self._outputs[key] = output
            return output_ref

        self._bindings[descriptor.capability_id] = _BoundCapability(
            manifest=manifest,
            handler=handler,
            canonical_handler=canonical_handler,
        )

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

    @staticmethod
    def _authority_ref(
        *,
        request: AssistantRequest,
        proposal: ToolProposal,
        grants: tuple[CapabilityGrant, ...],
        explicit_user_action: bool,
        requested_scopes: tuple[str, ...],
    ) -> str:
        return "assistant-authority:" + digest_json(
            {
                "request_digest": request.digest,
                "proposal_id": proposal.proposal_id,
                "capability_id": proposal.capability_id,
                "grant_scopes": sorted(
                    {
                        scope
                        for grant in grants
                        if grant.capability_id == proposal.capability_id
                        and grant.request_digest == request.digest
                        for scope in grant.granted_scopes
                    }
                ),
                "explicit_user_action": bool(explicit_user_action),
                "requested_scopes": sorted(set(requested_scopes)),
            }
        )

    async def _ensure_registered(self, binding: _BoundCapability) -> None:
        try:
            existing = await self.tool_runtime.manifest(binding.manifest.tool_id)
        except ToolNotFound:
            await self.tool_runtime.register(
                binding.manifest,
                binding.canonical_handler,
            )
            return
        if existing != binding.manifest:
            raise ToolCoordinatorError(
                "canonical tool manifest conflicts with assistant capability"
            )

    @staticmethod
    def _assistant_receipt(
        proposal: ToolProposal,
        request: AssistantRequest,
        canonical_receipt,
    ) -> ToolReceipt:
        status_map = {
            ToolExecutionStatus.SUCCEEDED: "succeeded",
            ToolExecutionStatus.FAILED: "failed",
            ToolExecutionStatus.DENIED: "blocked",
        }
        return ToolReceipt(
            proposal_id=proposal.proposal_id,
            capability_id=proposal.capability_id,
            status=status_map[canonical_receipt.status],
            output_ref=canonical_receipt.result_ref,
            request_digest=request.digest,
            arguments_digest=proposal.arguments_digest,
            started_at=canonical_receipt.started_at,
            finished_at=canonical_receipt.finished_at,
            error_code=canonical_receipt.error_code,
            provenance=(
                "assistant-capability-authorizer",
                "canonical-async-tool-runtime",
                f"canonical-receipt:{canonical_receipt.receipt_id}",
            ),
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

        encoded_arguments = json.dumps(
            dict(proposal.arguments),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded_arguments) > descriptor.max_input_bytes:
            raise ToolCoordinatorError("capability input exceeds declared bound")

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

        binding = self._proposal_binding(proposal)
        idempotency_scope = (request.digest, proposal.idempotency_key)
        prior_binding = self._idempotency_bindings.get(idempotency_scope)
        if prior_binding is not None and prior_binding != binding:
            raise ToolCoordinatorError(
                "idempotency key was reused for a different proposal"
            )

        count = self._request_call_counts.get(request.digest, 0)
        if prior_binding is None and count >= request.max_tool_calls:
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

        bound = self._bindings.get(proposal.capability_id)
        if bound is None:
            raise ToolCoordinatorError(
                f"no canonical handler bound for {proposal.capability_id!r}"
            )
        await self._ensure_registered(bound)

        operation_id = _canonical_operation_id(request)
        canonical_request = ToolExecutionRequest(
            request_id=_canonical_request_id(binding),
            operation_id=operation_id,
            tenant_id=request.tenant_id,
            tool_id=proposal.capability_id,
            idempotency_key=proposal.idempotency_key,
            arguments=dict(proposal.arguments),
            requested_at=instant,
            delegated_authority_ref=self._authority_ref(
                request=request,
                proposal=proposal,
                grants=grants,
                explicit_user_action=explicit_user_action,
                requested_scopes=requested_scopes,
            ),
        )
        if bound.manifest.approval_required:
            canonical_request = ToolExecutionRequest(
                request_id=canonical_request.request_id,
                operation_id=canonical_request.operation_id,
                tenant_id=canonical_request.tenant_id,
                tool_id=canonical_request.tool_id,
                idempotency_key=canonical_request.idempotency_key,
                arguments=canonical_request.arguments,
                requested_at=canonical_request.requested_at,
                approval_ref=approval_ref_for_request(canonical_request),
                delegated_authority_ref=canonical_request.delegated_authority_ref,
            )

        prior = await self.tool_runtime.receipt(
            tenant_id=canonical_request.tenant_id,
            operation_id=canonical_request.operation_id,
            idempotency_key=canonical_request.idempotency_key,
        )
        replayed = prior is not None
        if prior_binding is None:
            self._idempotency_bindings[idempotency_scope] = binding
            if not replayed:
                self._request_call_counts[request.digest] = count + 1

        canonical_receipt = await self.tool_runtime.execute(
            canonical_request,
            now=instant,
        )
        key = (
            canonical_request.tenant_id,
            canonical_request.operation_id,
            canonical_request.idempotency_key,
        )
        return ToolRunResult(
            receipt=self._assistant_receipt(
                proposal,
                request,
                canonical_receipt,
            ),
            output=self._outputs.get(key),
            replayed=replayed,
        )

    def reset_request_budget(self, request_digest: str) -> None:
        self._request_call_counts.pop(request_digest, None)


__all__ = [
    "CapabilityHandler",
    "ToolCoordinator",
    "ToolCoordinatorError",
    "ToolRunResult",
]
