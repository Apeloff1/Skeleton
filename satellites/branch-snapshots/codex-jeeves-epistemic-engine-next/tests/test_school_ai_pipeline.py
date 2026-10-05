from skeleton.school.ai_pipeline import PipelineKind, PipelineRequest, PipelineStage, plan_pipeline


def test_pipeline_is_teachable_and_verifiable():
    plan = plan_pipeline(
        PipelineRequest(
            kind=PipelineKind.DEBUG,
            objective="Find and explain the root cause of the failing parser.",
            learner_skill="debugging",
        )
    )
    stages = [step.stage for step in plan.steps]
    assert stages[0] == PipelineStage.UNDERSTAND
    assert PipelineStage.PLAN in stages
    assert PipelineStage.VERIFY in stages
    assert PipelineStage.EXPLAIN in stages
    assert PipelineStage.REFLECT in stages
    assert "claim_is_supported_by_measurement_or_reproduction" in plan.quality_gates
    assert "before/after technical evidence" in plan.learner_evidence


def test_pipeline_rejects_empty_objective():
    try:
        plan_pipeline(PipelineRequest(PipelineKind.TEXT_TO_CODE, "   "))
    except ValueError:
        return
    raise AssertionError("empty objectives must be rejected")
