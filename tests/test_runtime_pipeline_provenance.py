from skeleton.school.ai_pipeline import PipelineKind
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.session_runtime import JeevesSessionRuntime
from skeleton.school.student import StudentProfile


def test_runtime_records_pipeline_contract_digest_in_policy_and_state():
    curriculum = CurriculumGraph()
    control = JeevesControlPlane(curriculum=curriculum)
    runtime = JeevesSessionRuntime(control=control, curriculum=curriculum)
    student = StudentProfile(student_id="s1", name="Learner")

    plan = runtime.begin(student, session_id="pipeline-provenance", pipeline_kind=PipelineKind.DEBUG)
    digest = plan.control.pipeline_contract_digest
    records = runtime.ledger.session("pipeline-provenance")
    orient = next(record for record in records if record.decision_id.endswith(":orient"))

    assert digest
    assert orient.state_digest
    assert orient.policy_digest
    assert digest in orient.state_digest
    assert digest in orient.policy_digest
    assert plan.pipeline_stages[0] == "understand"
    assert plan.pipeline_stages[-1] == "reflect"
