from skeleton.school.epistemics import (
    EpistemicEngine,
    EpistemicEvidence,
    EvidencePolarity,
    MisconceptionStage,
    contradiction_matrix,
)


def test_conflicting_evidence_is_explicit_and_confidence_bounded() -> None:
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("s", "recursion terminates", EvidencePolarity.SUPPORTS, step=1))
    update = engine.observe(EpistemicEvidence("r", "recursion terminates", EvidencePolarity.REFUTES, strength=0.9, step=2))
    assert update.contradiction
    assert update.belief.contradiction
    assert update.belief.confidence < 0.95


def test_decay_and_misconception_lifecycle_signal() -> None:
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("e", "x", EvidencePolarity.SUPPORTS, step=0))
    before = engine.beliefs["x"].confidence
    after = engine.decay(current_step=20)[0].confidence
    assert after != before
    engine.mark_misconception("x", MisconceptionStage.REPAIRING)
    assert engine.repair_signal("x") == "verify_transfer"


def test_contradiction_matrix() -> None:
    evidence = (
        EpistemicEvidence("a", "x", EvidencePolarity.SUPPORTS),
        EpistemicEvidence("b", "x", EvidencePolarity.REFUTES),
    )
    assert contradiction_matrix(evidence) == (("x", "support/refute"),)
