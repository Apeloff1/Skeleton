from skeleton.school.decision_policy import ArbitrationAction, EvidenceSignal, arbitrate
from skeleton.school.knowledge import KnowledgeState


def test_misconception_wins_over_escalation() -> None:
    state = KnowledgeState()
    state.observe("recursion", 0.95)
    state.mark_misconception("recursion", "base case is optional")
    result = arbitrate(state, "recursion", transfer_ready=True)
    assert result.action is ArbitrationAction.RETEACH


def test_low_energy_pauses_before_challenge() -> None:
    state = KnowledgeState(confidence={"x": 0.95})
    result = arbitrate(state, "x", energy=0.1)
    assert result.action is ArbitrationAction.PAUSE


def test_conflict_reduces_confidence() -> None:
    state = KnowledgeState(confidence={"x": 0.9})
    result = arbitrate(state, "x", signals=(EvidenceSignal("contradiction", 1.0),))
    assert result.action is ArbitrationAction.RETEACH
    assert result.confidence < 0.7
