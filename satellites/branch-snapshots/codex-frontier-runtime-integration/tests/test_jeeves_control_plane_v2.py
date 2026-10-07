from skeleton.school.counterfactual import CandidateAction, compete, default_candidates
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.outcomes import OutcomeKind, SessionOutcome
from skeleton.school.cs_pathways import next_pathway
from skeleton.school.debugging import DebugAction, DebuggingPolicy
from skeleton.school.code_intelligence import CodeIntelligenceEngine
from skeleton.school.student import StudentProfile
from skeleton.school.session_runtime import JeevesSessionRuntime
from skeleton.school.ai_pipeline import PipelineKind


def test_calibration_cannot_overpower_current_evidence():
    candidates = default_candidates(mastery=.1, contradiction=1.0, energy=1.0, transfer_ready=False)
    result = compete(candidates, reliability={"challenge": 1.0, "repair": 0.1})
    assert result.selected.action is CandidateAction.REPAIR


def test_control_plane_updates_policy_reliability_from_outcome():
    control = JeevesControlPlane(CurriculumGraph())
    student = StudentProfile(student_id="s1")
    before = control.policy_calibrator.reliability("practice")
    control.record_outcome(student, SessionOutcome("loops", .95, kind=OutcomeKind.INDEPENDENT), policy_action="practice")
    assert control.policy_calibrator.reliability("practice") > before


def test_runtime_executes_control_plane_policy_and_records_alternatives():
    curriculum = CurriculumGraph()
    control = JeevesControlPlane(curriculum)
    runtime = JeevesSessionRuntime(control, curriculum)
    plan = runtime.begin(StudentProfile(student_id="s1"), session_id="s1", query_terms=("algorithms",), pipeline_kind=PipelineKind.LESSON)
    assert plan.selected_policy == plan.control.policy_competition.selected.action.value
    rejected = [r for r in runtime.ledger.records if r.disposition.value == "rejected"]
    assert rejected
    runtime.ledger.verify()


def test_cs_pathway_normalizes_concept_prerequisite():
    assert next_pathway(("arrays_to_pools",)).pathway_id == "trees_to_spatial"
    assert next_pathway(("arrays and lists",)).pathway_id == "trees_to_spatial"


def test_debugging_priority_is_not_lexicographic():
    report = CodeIntelligenceEngine().analyze("def f(x):\n    return eval(x)\n")
    plan = DebuggingPolicy().plan(report)
    assert plan.next_step in {DebugAction.ISOLATE, DebugAction.REPRODUCE}

# Fresh PR push marker: the test suite is intentionally deterministic.
