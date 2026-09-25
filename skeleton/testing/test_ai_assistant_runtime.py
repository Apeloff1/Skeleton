from __future__ import annotations

from datetime import datetime, timezone

from skeleton.ai.assistant import (
    ArtifactKind,
    AssistantControlPlane,
    AssistantRequest,
    AutomationBuilder,
    AutomationPolicy,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityRegistry,
    ContextCandidate,
    IntentSignals,
    MemoryAction,
    MemoryCandidate,
    MemoryPolicy,
    MemorySensitivity,
    SideEffectClass,
    TrustTier,
)


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


def test_memory_policy_separates_retrieval_from_persistence() -> None:
    policy = MemoryPolicy()
    request = AssistantRequest(request_id="mem-1", text="What is 2 + 2?")
    ignored = policy.decide_retrieval(request, IntentSignals())
    assert ignored.action is MemoryAction.IGNORE

    retrieved = policy.decide_retrieval(
        request,
        IntentSignals(references_personal_history=True),
    )
    assert retrieved.action is MemoryAction.RETRIEVE

    sensitive = MemoryCandidate(
        content="sensitive user fact",
        source_ref="conversation:1",
        sensitivity=MemorySensitivity.SENSITIVE,
        useful_beyond_session=True,
    )
    assert policy.decide_persistence(sensitive).action is MemoryAction.IGNORE

    explicit = MemoryCandidate(
        content=sensitive.content,
        source_ref=sensitive.source_ref,
        sensitivity=MemorySensitivity.SENSITIVE,
        useful_beyond_session=True,
        explicit_user_request=True,
    )
    assert policy.decide_persistence(explicit).action is MemoryAction.SAVE


def test_automation_policy_rejects_subhour_recurring_watches() -> None:
    policy = AutomationPolicy()
    fast = AutomationBuilder.condition(
        title="Fast Watch",
        instruction="Check condition.",
        condition_description="condition becomes true",
        recurrence_vevent="BEGIN:VEVENT\nRRULE:FREQ=MINUTELY;INTERVAL=30\nEND:VEVENT",
    )
    assert policy.admit(fast).allowed is False

    hourly = AutomationBuilder.condition(
        title="Hourly Watch",
        instruction="Check condition.",
        condition_description="condition becomes true",
        recurrence_vevent="BEGIN:VEVENT\nRRULE:FREQ=HOURLY\nEND:VEVENT",
    )
    assert policy.admit(hourly).allowed is True


def test_control_plane_reports_missing_required_surface_then_resolves_it() -> None:
    registry = CapabilityRegistry()
    plane = AssistantControlPlane(registry=registry)
    request = AssistantRequest(
        request_id="run-1",
        text="What is the current release status?",
    )
    context = ContextCandidate(
        source_id="policy",
        content="Use current public evidence.",
        trust=TrustTier.TRUSTED_CONTROL,
        relevance=1.0,
        priority=100,
        provenance=("policy:v1",),
        observed_at=NOW,
    )

    preparation = plane.prepare(request, context_candidates=(context,))
    assert preparation.missing_required_capabilities == (CapabilityKind.PUBLIC_WEB,)
    assert preparation.ready_for_execution is False

    registry.register(
        CapabilityDescriptor(
            capability_id="public.web",
            kind=CapabilityKind.PUBLIC_WEB,
            side_effect=SideEffectClass.READ_ONLY,
        )
    )
    prepared = plane.prepare(request, context_candidates=(context,))
    assert prepared.missing_required_capabilities == ()
    assert prepared.ready_for_execution is True
    handoff = prepared.handoff(capability_ids=("public.web",), evidence_refs=("web:1",))
    assert handoff.request_digest == request.digest
    assert handoff.context_digest == prepared.context.digest

    run = plane.finalize(
        prepared,
        response_text="Current release status grounded in web:1.",
        capability_ids=("public.web",),
        evidence_refs=("web:1",),
    )
    assert run.request_digest == request.digest
    assert len(run.digest) == 64


def test_artifact_route_is_exposed_from_preparation() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDescriptor(
            capability_id="artifact.pdf",
            kind=CapabilityKind.ARTIFACT,
            side_effect=SideEffectClass.REVERSIBLE_WRITE,
        )
    )
    plane = AssistantControlPlane(registry=registry)
    request = AssistantRequest(request_id="run-2", text="Create a PDF report.")
    prepared = plane.prepare(request)
    assert prepared.signals.requests_artifact is ArtifactKind.PDF
    assert prepared.artifact_route is not None
    assert prepared.artifact_route.capability_id == "artifact.pdf"
