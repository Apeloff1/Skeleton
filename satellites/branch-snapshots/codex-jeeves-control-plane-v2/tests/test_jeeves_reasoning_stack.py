from skeleton.school.ai_pipeline import PipelineKind
from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.decision_ledger import DecisionLedger
from skeleton.school.epistemics import EpistemicEngine, EpistemicEvidence, EvidencePolarity
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.knowledge import KnowledgeGraph, KnowledgeNode, KnowledgeState, rank_knowledge
from skeleton.school.policy_calibration import PolicyCalibrator
from skeleton.school.session_runtime import JeevesSessionRuntime
from skeleton.school.student import StudentProfile


def test_epistemic_conflict_is_explicit_and_bounded() -> None:
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("support", "loops terminate", EvidencePolarity.SUPPORTS, strength=0.9))
    update = engine.observe(EpistemicEvidence("refute", "loops terminate", EvidencePolarity.REFUTES, strength=0.9))
    assert update.contradiction
    assert 0.0 < update.belief.confidence < 1.0
    assert engine.contradictions()


def test_ledger_hash_chain_is_replayable() -> None:
    ledger = DecisionLedger()
    ledger.append(session_id="s1", decision_id="d1", domain="school", action="practice", state={"mastery": 0.4}, policy={"confidence": 0.8})
    ledger.append(session_id="s1", decision_id="d2", domain="school", action="verify", predecessors=("d1",))
    ledger.verify()
    assert [r.decision_id for r in ledger.explain("d2")] == ["d1", "d2"]


def test_runtime_records_epistemic_evidence_and_ledger() -> None:
    curriculum = CurriculumGraph()
    runtime = JeevesSessionRuntime(JeevesControlPlane(curriculum), curriculum, KnowledgeGraph())
    runtime.begin(StudentProfile(student_id="s1"), session_id="s1", query_terms=("algorithms",), pipeline_kind=PipelineKind.LESSON)
    runtime.record_evidence(event="answer", subject="algorithms", claim="a loop always terminates", score=0.9, polarity=EvidencePolarity.SUPPORTS)
    assert runtime.epistemics.evidence
    runtime.ledger.verify()


def test_policy_calibration_updates_empirical_reliability() -> None:
    calibrator = PolicyCalibrator()
    baseline = calibrator.reliability("practice")
    calibrator.observe("practice", reward=1.0, successful=True)
    assert calibrator.reliability("practice") > baseline


def test_knowledge_ranking_promotes_misconception_repair() -> None:
    graph = KnowledgeGraph()
    graph.add_node(KnowledgeNode("graphs", "Graphs"))
    graph.add_node(KnowledgeNode("trees", "Trees"))
    state = KnowledgeState()
    state.mark_misconception("graphs", "confuses directed and undirected edges")
    ranked = rank_knowledge(graph, state, query_terms=("graphs",))
    assert ranked[0].node_id == "graphs"
