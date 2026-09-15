from skeleton.school.ai_pipeline import PipelineKind, PipelineRequest, plan_pipeline
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.session_runtime import JeevesSessionRuntime
from skeleton.school.student import StudentProfile


def test_runtime_exposes_exact_pipeline_and_plan_provenance():
    curriculum = CurriculumGraph()
    control = JeevesControlPlane(curriculum=curriculum)
    runtime = JeevesSessionRuntime(control=control, curriculum=curriculum)
    student = StudentProfile(student_id="s1", name="Learner")

    plan = runtime.begin(student, session_id="pipeline-provenance", pipeline_kind=PipelineKind.DEBUG)
    expected_pipeline = plan_pipeline(
        PipelineRequest(
            kind=PipelineKind.DEBUG,
            objective="advance the learner's current objective",
            learner_skill=None,
            require_tests=True,
        )
    )
    records = runtime.ledger.session("pipeline-provenance")
    orient = next(record for record in records if record.decision_id.endswith(":orient"))

    assert plan.pipeline_contract_digest == expected_pipeline.digest
    assert plan.provenance_digest == plan.control.provenance_digest
    assert len(orient.state_digest) == 64
    assert len(orient.policy_digest) == 64
    assert orient.state_digest != orient.policy_digest
    assert plan.pipeline_stages[0] == "understand"
    assert plan.pipeline_stages[-1] == "reflect"
