from skeleton.school.ai_pipeline import PipelineKind, PipelineStage, PipelineRequest, plan_pipeline


def test_pipeline_contract_is_valid_and_deterministic() -> None:
    request = PipelineRequest(kind=PipelineKind.DEBUG, objective="repair parser", learner_skill="python")
    first = plan_pipeline(request)
    second = plan_pipeline(request)

    assert first.validate() == ()
    assert first.digest == second.digest
    assert first.stages[0] is PipelineStage.UNDERSTAND
    assert first.stages[-1] is PipelineStage.REFLECT
    assert PipelineStage.VERIFY in first.stages
    assert "claim_is_supported_by_measurement_or_reproduction" in first.quality_gates


def test_pipeline_rejects_malformed_contract() -> None:
    from skeleton.school.ai_pipeline import PipelinePlan, PipelineStep

    malformed = PipelinePlan(
        PipelineKind.LESSON,
        (PipelineStep(PipelineStage.GENERATE, "generate"),),
        ("verification_evidence_present",),
        (),
    )
    assert malformed.validate() == (
        "understand_must_be_first",
        "reflect_must_be_last",
        "verification_gate_requires_verify_stage",
    )
