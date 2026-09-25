"""Composable product-assistant control plane over existing Skeleton runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .artifacts import ArtifactRoute, ArtifactRouter
from .automation import AutomationPolicy
from .capabilities import CapabilityRegistry
from .context import ContextCompiler
from .contracts import (
    AssistantRequest,
    CapabilityKind,
    CompiledContext,
    ContextCandidate,
    IntentSignals,
    RoutingPlan,
    ToolReceipt,
)
from .handoff import AssistantHandoff, build_handoff
from .memory import MemoryDecision, MemoryPolicy
from .provenance import AssistantRunRecord, ProvenanceBuilder
from .routing import AssistantRouter, infer_signals
from .tooling import ToolCoordinator


@dataclass(frozen=True, slots=True)
class AssistantPreparation:
    request: AssistantRequest
    signals: IntentSignals
    route: RoutingPlan
    context: CompiledContext | None
    memory_decision: MemoryDecision
    artifact_route: ArtifactRoute | None
    missing_required_capabilities: tuple[CapabilityKind, ...]

    @property
    def ready_for_execution(self) -> bool:
        return not self.missing_required_capabilities

    def handoff(
        self,
        *,
        capability_ids: Iterable[str] = (),
        evidence_refs: Iterable[str] = (),
    ) -> AssistantHandoff:
        return build_handoff(
            self.request,
            self.route,
            context=self.context,
            capability_ids=capability_ids,
            evidence_refs=evidence_refs,
        )


class AssistantControlPlane:
    """High-level composition layer; model execution remains downstream.

    This class intentionally does not expose or depend on hidden reasoning text.
    It records structured routing and provenance decisions sufficient for replay.
    """

    _INTRINSIC = {
        CapabilityKind.DIRECT_REASONING,
    }

    def __init__(
        self,
        *,
        registry: CapabilityRegistry | None = None,
        router: AssistantRouter | None = None,
        context_compiler: ContextCompiler | None = None,
        memory_policy: MemoryPolicy | None = None,
        artifact_router: ArtifactRouter | None = None,
        automation_policy: AutomationPolicy | None = None,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.router = router or AssistantRouter()
        self.context_compiler = context_compiler or ContextCompiler()
        self.memory_policy = memory_policy or MemoryPolicy()
        self.artifact_router = artifact_router or ArtifactRouter()
        self.automation_policy = automation_policy or AutomationPolicy()
        self.tools = ToolCoordinator(self.registry)

    def _missing_required(self, route: RoutingPlan) -> tuple[CapabilityKind, ...]:
        missing: list[CapabilityKind] = []
        for step in route.steps:
            if not step.required or step.capability in self._INTRINSIC:
                continue
            if not self.registry.by_kind(step.capability) and step.capability not in missing:
                missing.append(step.capability)
        return tuple(missing)

    def prepare(
        self,
        request: AssistantRequest,
        *,
        signals: IntentSignals | None = None,
        context_candidates: Iterable[ContextCandidate] = (),
        compile_context: bool = True,
        allow_restricted_context: bool = False,
    ) -> AssistantPreparation:
        observed = infer_signals(request) if signals is None else signals
        route = self.router.plan(request, observed)
        memory_decision = self.memory_policy.decide_retrieval(request, observed)

        context = None
        if compile_context:
            context = self.context_compiler.compile(
                request,
                context_candidates,
                allow_restricted=allow_restricted_context,
            )

        artifact_route = (
            None
            if observed.requests_artifact is None
            else self.artifact_router.resolve(observed.requests_artifact)
        )

        return AssistantPreparation(
            request=request,
            signals=observed,
            route=route,
            context=context,
            memory_decision=memory_decision,
            artifact_route=artifact_route,
            missing_required_capabilities=self._missing_required(route),
        )

    def finalize(
        self,
        preparation: AssistantPreparation,
        *,
        response_text: str,
        capability_ids: Iterable[str] = (),
        tool_receipts: Iterable[ToolReceipt] = (),
        evidence_refs: Iterable[str] = (),
    ) -> AssistantRunRecord:
        if not isinstance(preparation, AssistantPreparation):
            raise TypeError("preparation must be AssistantPreparation")
        return ProvenanceBuilder.build(
            request_digest=preparation.request.digest,
            route=preparation.route,
            response_text=response_text,
            context_digest=(
                None if preparation.context is None else preparation.context.digest
            ),
            capability_ids=capability_ids,
            tool_receipts=tool_receipts,
            evidence_refs=evidence_refs,
        )


__all__ = [
    "AssistantControlPlane",
    "AssistantPreparation",
]
