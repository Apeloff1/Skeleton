import pytest

from skeleton.school.epistemics import EpistemicEngine, EpistemicEvidence, EvidencePolarity


def test_supersession_replaces_active_evidence_once():
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("e1", "claim", EvidencePolarity.SUPPORTS))
    engine.supersede("e1", replacement_id="e2", strength=0.8)

    assert tuple(item.evidence_id for item in engine.active_evidence("claim")) == ("e2",)

    with pytest.raises(ValueError, match="already superseded"):
        engine.supersede("e1", replacement_id="e3")


def test_supersession_rejects_duplicate_replacement_id():
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("e1", "claim", EvidencePolarity.SUPPORTS))
    engine.observe(EpistemicEvidence("e2", "claim", EvidencePolarity.SUPPORTS))

    with pytest.raises(ValueError, match="duplicate evidence id"):
        engine.supersede("e1", replacement_id="e2")


def test_superseded_evidence_stays_in_history_but_not_belief_inputs():
    engine = EpistemicEngine()
    engine.observe(EpistemicEvidence("e1", "claim", EvidencePolarity.SUPPORTS))
    engine.supersede("e1", replacement_id="e2", strength=0.6)

    assert set(engine.evidence) == {"e1", "e2"}
    assert engine.beliefs["claim"].evidence_ids == ("e2",)
