from __future__ import annotations

from skeleton.ai.assistant import (
    ArtifactKind,
    AssistantRequest,
    AssistantRouter,
    CapabilityKind,
    infer_signals,
)


def _request(text: str, **kwargs) -> AssistantRequest:
    return AssistantRequest(request_id="req-routing", text=text, **kwargs)


def test_fresh_information_requires_public_web_before_synthesis() -> None:
    request = _request("What is the latest release and current status?")
    plan = AssistantRouter().plan(request)
    assert plan.steps[0].capability is CapabilityKind.PUBLIC_WEB
    assert plan.steps[0].required is True
    assert plan.steps[-1].capability is CapabilityKind.DIRECT_REASONING
    assert plan.direct_answer_allowed is False


def test_attached_pdf_read_does_not_become_pdf_creation() -> None:
    request = _request(
        "Summarize the attached PDF.",
        attachment_refs=("file:report.pdf",),
    )
    signals = infer_signals(request)
    assert signals.references_files is True
    assert signals.requests_artifact is None
    plan = AssistantRouter().plan(request, signals)
    kinds = [step.capability for step in plan.steps]
    assert CapabilityKind.FILES in kinds
    assert CapabilityKind.ARTIFACT not in kinds


def test_explicit_artifact_creation_routes_to_artifact_plane() -> None:
    request = _request("Create a PDF report from these notes.")
    signals = infer_signals(request)
    assert signals.requests_artifact is ArtifactKind.PDF
    plan = AssistantRouter().plan(request, signals)
    assert CapabilityKind.ARTIFACT in [step.capability for step in plan.steps]


def test_tomorrow_information_query_is_not_mistaken_for_automation() -> None:
    request = _request("What will the weather be tomorrow?")
    signals = infer_signals(request)
    assert signals.requests_future_action is False
    assert signals.needs_fresh_public_info is True


def test_monitor_request_requires_automation_confirmation_without_explicit_allow() -> None:
    request = _request("Monitor this issue and notify me when it closes.")
    plan = AssistantRouter().plan(request)
    assert CapabilityKind.AUTOMATION in [step.capability for step in plan.steps]
    assert plan.requires_user_confirmation is True

    allowed = AssistantRequest(
        request_id="req-routing-allowed",
        text=request.text,
        explicitly_allowed_capabilities=frozenset({CapabilityKind.AUTOMATION}),
    )
    assert AssistantRouter().plan(allowed).requires_user_confirmation is False
