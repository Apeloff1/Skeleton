"""A pipeline that has not run did not finish in zero milliseconds."""

from skeleton.intelligence.pipeline_orchestrator import PipelineOrchestrator, PipelineStage


def test_unrun_card_has_no_duration() -> None:
    pipeline = PipelineOrchestrator("build")
    pipeline.add_stage(PipelineStage("compile", lambda value: value))
    assert pipeline.card()["duration_ms"] is None
    ran = pipeline.execute(1)
    assert isinstance(ran["duration_ms"], float)
    assert ran["duration_ms"] >= 0
