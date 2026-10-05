from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.epistemics import EpistemicEvidence, EvidencePolarity
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.student import StudentProfile


def test_jeeves_exposes_policy_competition() -> None:
    control = JeevesControlPlane(CurriculumGraph())
    control.epistemics.observe(EpistemicEvidence("e1", "graphs", EvidencePolarity.SUPPORTS, strength=0.9))
    control.epistemics.observe(EpistemicEvidence("e2", "graphs", EvidencePolarity.REFUTES, strength=0.9))
    plan = control.plan(StudentProfile("s1"), query_terms=("graphs",))
    assert plan.policy_competition is not None
    assert plan.policy_competition.selected.action.value == "repair"
    assert any(decision.domain == "policy_competition" for decision in plan.decisions)
