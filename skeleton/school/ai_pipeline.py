"""Provider-neutral AI pipeline planning for Jeeves.

Rebuilds the useful orchestration idea from Tutolage's AI pipeline without
coupling Skeleton to FastAPI, credentials, a vendor SDK, or a specific model.
The output is a typed execution plan that can later be handed to any model or
tool adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class PipelineKind(str, Enum):
    TEXT_TO_CODE = "text_to_code"
    CODE_TO_EXPLANATION = "code_to_explanation"
    CODE_TO_TESTS = "code_to_tests"
    CODE_TO_DOCS = "code_to_docs"
    CODE_TO_APP = "code_to_app"
    CODE_TO_GAME = "code_to_game"
    REFACTOR = "refactor"
    DEBUG = "debug"
    OPTIMIZE = "optimize"
    LESSON = "lesson"
    ASSESS = "assess"


class PipelineStage(str, Enum):
    UNDERSTAND = "understand"
    PLAN = "plan"
    GENERATE = "generate"
    VERIFY = "verify"
    EXPLAIN = "explain"
    REFLECT = "reflect"


@dataclass(frozen=True)
class PipelineRequest:
    kind: PipelineKind
    objective: str
    context: str = ""
    constraints: tuple[str, ...] = ()
    learner_skill: str | None = None
    require_tests: bool = True
    require_explanation: bool = True


@dataclass(frozen=True)
class PipelineStep:
    stage: PipelineStage
    instruction: str
    required: bool = True


@dataclass(frozen=True)
class PipelinePlan:
    kind: PipelineKind
    steps: tuple[PipelineStep, ...]
    quality_gates: tuple[str, ...]
    learner_evidence: tuple[str, ...]


def plan_pipeline(request: PipelineRequest) -> PipelinePlan:
    """Turn an intent into a safe, teachable, verifiable execution graph."""
    if not request.objective.strip():
        raise ValueError("objective cannot be empty")

    steps = [
        PipelineStep(PipelineStage.UNDERSTAND, "Restate the objective, inputs, outputs, constraints, and success criteria."),
        PipelineStep(PipelineStage.PLAN, "Choose an approach and expose the key trade-offs before implementation."),
        PipelineStep(PipelineStage.GENERATE, f"Perform the {request.kind.value} task while preserving learner ownership."),
    ]
    if request.require_tests or request.kind in {PipelineKind.DEBUG, PipelineKind.REFACTOR, PipelineKind.OPTIMIZE}:
        steps.append(PipelineStep(PipelineStage.VERIFY, "Run or construct the smallest meaningful verification and inspect failure evidence."))
    if request.require_explanation:
        steps.append(PipelineStep(PipelineStage.EXPLAIN, "Explain the result at the learner's current skill level and surface assumptions."))
    steps.append(PipelineStep(PipelineStage.REFLECT, "Capture what changed, what evidence supports it, and what should happen next."))

    gates = ["objective_contract_present", "constraints_respected", "result_matches_requested_output"]
    if request.require_tests:
        gates.append("verification_evidence_present")
    if request.kind in {PipelineKind.DEBUG, PipelineKind.OPTIMIZE}:
        gates.append("claim_is_supported_by_measurement_or_reproduction")
    if request.learner_skill:
        gates.append("difficulty_is_appropriate_for_learner")

    evidence = ["artifact/result quality", "learner reasoning", "verification outcome"]
    if request.kind in {PipelineKind.DEBUG, PipelineKind.REFACTOR, PipelineKind.OPTIMIZE}:
        evidence.append("before/after technical evidence")
    if request.kind in {PipelineKind.LESSON, PipelineKind.ASSESS}:
        evidence.append("independent learner response")

    return PipelinePlan(request.kind, tuple(steps), tuple(dict.fromkeys(gates)), tuple(dict.fromkeys(evidence)))


def pipeline_capabilities() -> Mapping[PipelineKind, tuple[PipelineStage, ...]]:
    """Expose the canonical stage graph for adapters and UI layers."""
    return {kind: tuple(step.stage for step in plan_pipeline(PipelineRequest(kind, "placeholder" )).steps) for kind in PipelineKind}
