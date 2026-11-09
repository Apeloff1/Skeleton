"""Deterministic request-surface routing for the assistant control plane."""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Iterable, Mapping

from .contracts import (
    ArtifactKind,
    AssistantRequest,
    CapabilityKind,
    CapabilityPlanStep,
    IntentSignals,
    RoutingPlan,
)


_FRESH = re.compile(
    r"\b(latest|current|today|tonight|now|recent|news|weather|forecast|score|"
    r"standings|price|prices|availability|open now|law|regulation|release|version)\b",
    re.IGNORECASE,
)
_PERSONAL = re.compile(
    r"\b(remember|recall|we discussed|we talked|last time|my previous|my earlier|"
    r"continue where|you should know|from our chats|my preferences?)\b",
    re.IGNORECASE,
)
_FILE = re.compile(
    r"\b(attached|attachment|uploaded|my file|this file|the document|the pdf|"
    r"spreadsheet|workbook|deck|presentation)\b",
    re.IGNORECASE,
)
_EXTERNAL_ACTION = re.compile(
    r"\b(send|email|book|reserve|cancel|reschedule|create event|update issue|"
    r"merge pull request|merge pr|push|commit|post|publish|delete|archive|"
    r"label|reply to|forward|purchase|order)\b",
    re.IGNORECASE,
)
_FUTURE = re.compile(
    r"\b(remind me|notify me|every (day|week|month|hour)|each (day|week|month)|"
    r"when .* becomes|monitor|watch for|in \d+ (minutes?|hours?|days?))\b",
    re.IGNORECASE,
)
_CREATE_ARTIFACT = re.compile(
    r"\b(create|make|generate|build|produce|draft|write|prepare|export|render|design)\b",
    re.IGNORECASE,
)
_IMAGE = re.compile(
    r"\b(generate|create|draw|render|design|visualize|edit|retouch|upscale)\b.*\b"
    r"(image|photo|picture|illustration|diagram|poster|logo|portrait)\b",
    re.IGNORECASE,
)
_CODE_EXEC = re.compile(
    r"\b(run|execute|benchmark|calculate with python|plot|chart from data|"
    r"analy[sz]e this dataset|simulate)\b",
    re.IGNORECASE,
)


_ARTIFACT_PATTERNS: tuple[tuple[ArtifactKind, re.Pattern[str]], ...] = (
    (
        ArtifactKind.SPREADSHEET,
        re.compile(r"\b(spreadsheet|xlsx|excel workbook|financial model)\b", re.IGNORECASE),
    ),
    (
        ArtifactKind.PRESENTATION,
        re.compile(r"\b(presentation|slides?|pptx|slide deck)\b", re.IGNORECASE),
    ),
    (
        ArtifactKind.PDF,
        re.compile(r"\b(pdf|portable document)\b", re.IGNORECASE),
    ),
    (
        ArtifactKind.DOCUMENT,
        re.compile(r"\b(document|docx|report|memo|letter|proposal)\b", re.IGNORECASE),
    ),
)


def _metadata_bool(metadata: Mapping[str, object], key: str) -> bool | None:
    value = metadata.get(key)
    return value if isinstance(value, bool) else None


def _artifact_from_metadata(metadata: Mapping[str, object]) -> ArtifactKind | None:
    raw = metadata.get("artifact_kind")
    if raw is None:
        return None
    try:
        return raw if isinstance(raw, ArtifactKind) else ArtifactKind(str(raw))
    except ValueError:
        return None


def infer_signals(request: AssistantRequest) -> IntentSignals:
    """Infer only routing-level signals; never infer permissions or authority."""

    text = request.text
    metadata = request.metadata

    artifact = _artifact_from_metadata(metadata)
    if artifact is None and _CREATE_ARTIFACT.search(text):
        for kind, pattern in _ARTIFACT_PATTERNS:
            if pattern.search(text):
                artifact = kind
                break

    hints: list[CapabilityKind] = []
    raw_hints = metadata.get("capability_hints", ())
    if isinstance(raw_hints, (list, tuple, set, frozenset)):
        for raw in raw_hints:
            try:
                hint = raw if isinstance(raw, CapabilityKind) else CapabilityKind(str(raw))
            except ValueError:
                continue
            if hint not in hints:
                hints.append(hint)

    def signal(key: str, inferred: bool) -> bool:
        override = _metadata_bool(metadata, key)
        return inferred if override is None else override

    return IntentSignals(
        needs_fresh_public_info=signal(
            "needs_fresh_public_info", bool(_FRESH.search(text))
        ),
        references_personal_history=signal(
            "references_personal_history", bool(_PERSONAL.search(text))
        ),
        references_files=signal(
            "references_files", bool(request.attachment_refs) or bool(_FILE.search(text))
        ),
        requests_external_action=signal(
            "requests_external_action", bool(_EXTERNAL_ACTION.search(text))
        ),
        requests_artifact=artifact,
        requests_future_action=signal(
            "requests_future_action", bool(_FUTURE.search(text))
        ),
        requests_image=signal("requests_image", bool(_IMAGE.search(text))),
        requests_code_execution=signal(
            "requests_code_execution", bool(_CODE_EXEC.search(text))
        ),
        sensitive_context=signal(
            "sensitive_context", bool(metadata.get("sensitive_context", False))
        ),
        explicit_capability_hints=tuple(hints),
    )


class AssistantRouter:
    """Build a bounded, explainable capability plan from request-level signals."""

    _READ_CAPABILITIES = {
        CapabilityKind.PUBLIC_WEB,
        CapabilityKind.PERSONAL_CONTEXT,
        CapabilityKind.FILES,
    }

    def plan(
        self,
        request: AssistantRequest,
        signals: IntentSignals | None = None,
    ) -> RoutingPlan:
        observed = infer_signals(request) if signals is None else signals
        ordered: list[tuple[CapabilityKind, bool, str, bool]] = []

        def add(
            capability: CapabilityKind,
            *,
            required: bool,
            reason: str,
            read_only: bool,
        ) -> None:
            if any(item[0] is capability for item in ordered):
                return
            ordered.append((capability, required, reason, read_only))

        # Retrieval comes first so downstream reasoning and action operate on
        # authoritative/fresh context rather than model recollection.
        if observed.references_personal_history:
            add(
                CapabilityKind.PERSONAL_CONTEXT,
                required=True,
                reason="personal-history-reference",
                read_only=True,
            )
        if observed.references_files:
            add(
                CapabilityKind.FILES,
                required=True,
                reason="file-evidence-reference",
                read_only=True,
            )
        if observed.needs_fresh_public_info:
            add(
                CapabilityKind.PUBLIC_WEB,
                required=True,
                reason="fresh-public-information",
                read_only=True,
            )

        # Explicit hints may add capabilities but never remove inferred required
        # evidence dependencies.
        for hint in observed.explicit_capability_hints:
            add(
                hint,
                required=False,
                reason="explicit-capability-hint",
                read_only=hint in self._READ_CAPABILITIES
                or hint is CapabilityKind.DIRECT_REASONING,
            )

        if observed.requests_code_execution:
            add(
                CapabilityKind.CODE_EXECUTION,
                required=True,
                reason="deterministic-computation-request",
                read_only=False,
            )
        if observed.requests_image:
            add(
                CapabilityKind.IMAGE_GENERATION,
                required=True,
                reason="image-generation-request",
                read_only=False,
            )
        if observed.requests_artifact is not None:
            add(
                CapabilityKind.ARTIFACT,
                required=True,
                reason=f"artifact-{observed.requests_artifact.value}",
                read_only=False,
            )
        if observed.requests_external_action:
            add(
                CapabilityKind.EXTERNAL_APP,
                required=True,
                reason="external-side-effect-request",
                read_only=False,
            )
        if observed.requests_future_action:
            add(
                CapabilityKind.AUTOMATION,
                required=True,
                reason="future-or-recurring-action",
                read_only=False,
            )

        # Direct reasoning remains the final synthesis step. It is marked
        # required only when no external capability is required.
        external_required = any(
            required and capability is not CapabilityKind.DIRECT_REASONING
            for capability, required, _, _ in ordered
        )
        add(
            CapabilityKind.DIRECT_REASONING,
            required=not external_required,
            reason="synthesis",
            read_only=True,
        )

        steps = tuple(
            CapabilityPlanStep(
                capability=capability,
                required=required,
                reason_code=reason,
                order=index,
                read_only=read_only,
            )
            for index, (capability, required, reason, read_only) in enumerate(ordered)
        )

        consequential = {
            CapabilityKind.EXTERNAL_APP,
            CapabilityKind.AUTOMATION,
        }
        requires_confirmation = any(
            step.capability in consequential
            and step.capability not in request.explicitly_allowed_capabilities
            for step in steps
        )

        return RoutingPlan(
            request_digest=request.digest,
            steps=steps,
            direct_answer_allowed=not external_required,
            requires_user_confirmation=requires_confirmation,
        )


__all__ = ["AssistantRouter", "infer_signals"]
